#!/usr/bin/env python3
"""Standalone RDS Blue-Green status & swap utility for AIS (EKS-ready).

Tracks the active RDS instance (`blue` or `green`) in AWS SSM Parameter Store
and optionally updates a Route53 DB CNAME record if configured. Performs
pre-swap RDS availability and PostgreSQL row-count sanity checks before
flipping.

Usage:
    python3 scripts/rds_blue_green.py status
    python3 scripts/rds_blue_green.py active-color
    python3 scripts/rds_blue_green.py inactive-color
    python3 scripts/rds_blue_green.py wait --target green
    python3 scripts/rds_blue_green.py swap --dry-run
    python3 scripts/rds_blue_green.py swap
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

import boto3
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
if (REPO_ROOT / ".env").is_file():
    load_dotenv(REPO_ROOT / ".env", override=False)

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
SSM_COLOR_PARAM = os.environ.get("RDS_ACTIVE_COLOR_SSM_PARAM", "/ais/prod/active_rds_color")
SSM_HOST_PARAM = os.environ.get("RDS_ACTIVE_HOST_SSM_PARAM", "/ais/prod/active_rds_host")
ROUTE53_ZONE_ID = os.environ.get("RDS_ROUTE53_ZONE_ID", "").strip()
RDS_ACTIVE_CNAME = os.environ.get("RDS_ACTIVE_CNAME", "").strip()
RDS_STAGING_CNAME = os.environ.get("RDS_STAGING_CNAME", "").strip()
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "").strip()

RDS_IDENTIFIERS = {
    "blue": os.environ.get("BLUE_RDS_IDENTIFIER", "ais-engine-blue"),
    "green": os.environ.get("GREEN_RDS_IDENTIFIER", "ais-engine-green"),
    "dev": os.environ.get("DEV_RDS_IDENTIFIER", "ais-engine-dev"),
}


def get_rds_info(rds_client, target: str) -> dict:
    identifier = RDS_IDENTIFIERS[target]
    resp = rds_client.describe_db_instances(DBInstanceIdentifier=identifier)
    inst = resp["DBInstances"][0]
    return {
        "target": target,
        "identifier": identifier,
        "status": inst["DBInstanceStatus"],
        "endpoint": inst["Endpoint"]["Address"],
        "port": inst["Endpoint"]["Port"],
    }


def get_active_color(ssm_client) -> str:
    try:
        resp = ssm_client.get_parameter(Name=SSM_COLOR_PARAM)
        color = resp["Parameter"]["Value"].strip().lower()
        if color in ("blue", "green"):
            return color
        raise ValueError(f"Unexpected SSM value for {SSM_COLOR_PARAM}: {color!r}")
    except ssm_client.exceptions.ParameterNotFound:
        raise RuntimeError(
            f"SSM parameter {SSM_COLOR_PARAM!r} not found. "
            "Initialize it with `aws ssm put-parameter --name "
            f"{SSM_COLOR_PARAM} --type String --value blue` (or green)."
        )


def other_color(color: str) -> str:
    return "green" if color == "blue" else "blue"


def wait_for_rds_available(rds_client, target: str, timeout_seconds: int = 900, poll_seconds: int = 15) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while True:
        info = get_rds_info(rds_client, target)
        if info["status"] == "available":
            return info
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"RDS instance {info['identifier']} stayed in status {info['status']!r} "
                f"after {timeout_seconds}s"
            )
        print(f"Waiting for {info['identifier']} (status={info['status']})...", flush=True)
        time.sleep(poll_seconds)


def check_db_health(host: str) -> dict:
    import psycopg2

    password = os.environ.get("RDS_ENGINE_DB_PASS") or os.environ.get("ENGINE_DB_PASS")
    if not password:
        raise RuntimeError("RDS_ENGINE_DB_PASS (or ENGINE_DB_PASS) is required for DB health check")
    user = os.environ.get("RDS_ENGINE_DB_USER", "ais_engine")
    dbname = os.environ.get("RDS_ENGINE_DB_NAME", "ais_engine")

    conn = psycopg2.connect(host=host, user=user, password=password, dbname=dbname, connect_timeout=10)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM address_summary")
            addr_count = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM geocode")
            geo_count = cur.fetchone()[0]
            cur.execute("SELECT pg_database_size(current_database())")
            size_bytes = cur.fetchone()[0]
    finally:
        conn.close()

    if addr_count < 500_000:
        raise RuntimeError(f"Target DB {host} failed sanity check: address_summary has only {addr_count} rows")
    if geo_count < 500_000:
        raise RuntimeError(f"Target DB {host} failed sanity check: geocode has only {geo_count} rows")

    return {
        "address_summary_rows": addr_count,
        "geocode_rows": geo_count,
        "size_gb": round(size_bytes / (1024**3), 2),
    }


def update_route53_cnames(route53_client, new_active_host: str, new_staging_host: str, dry_run: bool) -> None:
    if not (ROUTE53_ZONE_ID and RDS_ACTIVE_CNAME):
        return
    changes = [
        {
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": RDS_ACTIVE_CNAME.rstrip(".") + ".",
                "Type": "CNAME",
                "TTL": 30,
                "ResourceRecords": [{"Value": new_active_host}],
            },
        }
    ]
    if RDS_STAGING_CNAME:
        changes.append(
            {
                "Action": "UPSERT",
                "ResourceRecordSet": {
                    "Name": RDS_STAGING_CNAME.rstrip(".") + ".",
                    "Type": "CNAME",
                    "TTL": 30,
                    "ResourceRecords": [{"Value": new_staging_host}],
                },
            }
        )

    if dry_run:
        print(f"[dry-run] Would update Route53 zone {ROUTE53_ZONE_ID}: {json.dumps(changes)}")
        return

    route53_client.change_resource_record_sets(
        HostedZoneId=ROUTE53_ZONE_ID,
        ChangeBatch={"Comment": "AIS RDS blue-green swap", "Changes": changes},
    )
    print(f"Updated Route53 CNAME {RDS_ACTIVE_CNAME} -> {new_active_host}")


def notify_teams(message: str) -> None:
    if not TEAMS_WEBHOOK_URL:
        return
    payload = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(
        TEAMS_WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as exc:
        print(f"Warning: failed to send Teams notification: {exc}", file=sys.stderr)


def cmd_status(args) -> int:
    rds = boto3.client("rds", region_name=AWS_REGION)
    ssm = boto3.client("ssm", region_name=AWS_REGION)

    active = get_active_color(ssm)
    inactive = other_color(active)
    blue = get_rds_info(rds, "blue")
    green = get_rds_info(rds, "green")

    print(json.dumps({"active": active, "inactive": inactive, "blue": blue, "green": green}, indent=2))
    return 0


def cmd_color(args, which: str) -> int:
    ssm = boto3.client("ssm", region_name=AWS_REGION)
    active = get_active_color(ssm)
    print(active if which == "active" else other_color(active))
    return 0


def cmd_wait(args) -> int:
    rds = boto3.client("rds", region_name=AWS_REGION)
    info = wait_for_rds_available(rds, args.target, timeout_seconds=args.timeout)
    print(f"RDS {info['identifier']} is available at {info['endpoint']}")
    return 0


def cmd_swap(args) -> int:
    rds = boto3.client("rds", region_name=AWS_REGION)
    ssm = boto3.client("ssm", region_name=AWS_REGION)

    current_active = get_active_color(ssm)
    target_color = args.target or other_color(current_active)

    if target_color == current_active and not args.force:
        print(f"Active RDS is already '{current_active}'. Pass --force to rewrite anyway.")
        return 0

    target_info = get_rds_info(rds, target_color)
    current_info = get_rds_info(rds, current_active)

    if target_info["status"] != "available":
        raise RuntimeError(
            f"Cannot swap to {target_info['identifier']}: status is {target_info['status']!r}"
        )

    if not args.skip_health_check:
        health = check_db_health(target_info["endpoint"])
        print(f"Health check passed for {target_info['identifier']}: {health}")

    if args.dry_run:
        print(
            f"[dry-run] Would swap active RDS from {current_active} ({current_info['endpoint']}) "
            f"to {target_color} ({target_info['endpoint']})"
        )
        print(f"[dry-run] Would set SSM {SSM_COLOR_PARAM}={target_color}")
        print(f"[dry-run] Would set SSM {SSM_HOST_PARAM}={target_info['endpoint']}")
    else:
        ssm.put_parameter(Name=SSM_COLOR_PARAM, Value=target_color, Type="String", Overwrite=True)
        ssm.put_parameter(Name=SSM_HOST_PARAM, Value=target_info["endpoint"], Type="String", Overwrite=True)
        print(f"Updated SSM parameters: {SSM_COLOR_PARAM}={target_color}, {SSM_HOST_PARAM}={target_info['endpoint']}")

    if ROUTE53_ZONE_ID and RDS_ACTIVE_CNAME:
        route53 = boto3.client("route53", region_name=AWS_REGION)
        update_route53_cnames(route53, target_info["endpoint"], current_info["endpoint"], dry_run=args.dry_run)

    if not args.dry_run:
        msg = (
            f"AIS RDS Blue-Green swap complete: active RDS is now {target_color} "
            f"({target_info['endpoint']}); previous active ({current_active}) is now staging."
        )
        print(msg)
        notify_teams(msg)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AIS RDS Blue-Green management utility")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show active/inactive RDS colors and instance status")
    sub.add_parser("active-color", help="Print currently active RDS color (blue or green)")
    sub.add_parser("inactive-color", help="Print currently inactive/staging RDS color")

    wait_p = sub.add_parser("wait", help="Wait until an RDS instance becomes available")
    wait_p.add_argument("--target", choices=("blue", "green", "dev"), required=True)
    wait_p.add_argument("--timeout", type=int, default=900)

    swap_p = sub.add_parser("swap", help="Swap the active RDS pointer to the inactive (or specified) instance")
    swap_p.add_argument("--target", choices=("blue", "green"), default=None)
    swap_p.add_argument("--skip-health-check", action="store_true")
    swap_p.add_argument("--dry-run", action="store_true")
    swap_p.add_argument("--force", action="store_true")

    args = parser.parse_args()
    if args.command == "status":
        return cmd_status(args)
    if args.command == "active-color":
        return cmd_color(args, "active")
    if args.command == "inactive-color":
        return cmd_color(args, "inactive")
    if args.command == "wait":
        return cmd_wait(args)
    if args.command == "swap":
        return cmd_swap(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
