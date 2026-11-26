"""Unit tests for the RDS Blue-Green swap CLI (`scripts/rds_blue_green.py`)."""

import argparse
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Load scripts/rds_blue_green.py by file path (scripts/ is not a Python package)
_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "rds_blue_green.py"
_spec = importlib.util.spec_from_file_location("rds_blue_green", _SCRIPT_PATH)
rbg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rbg)


def test_other_color():
    assert rbg.other_color("blue") == "green"
    assert rbg.other_color("green") == "blue"


def test_get_active_color_valid_and_invalid():
    """Reads blue/green from SSM and raises cleanly on unexpected values."""
    ssm = MagicMock()
    ssm.exceptions.ParameterNotFound = KeyError
    ssm.get_parameter.return_value = {"Parameter": {"Value": "Blue"}}
    assert rbg.get_active_color(ssm) == "blue"

    ssm.get_parameter.return_value = {"Parameter": {"Value": "purple"}}
    with pytest.raises(ValueError, match="Unexpected SSM value"):
        rbg.get_active_color(ssm)


def test_swap_dry_run_does_not_mutate_ssm(monkeypatch):
    """Dry-run swap checks RDS availability without writing SSM parameters."""
    rds = MagicMock()
    ssm = MagicMock()
    ssm.exceptions.ParameterNotFound = KeyError
    ssm.get_parameter.return_value = {"Parameter": {"Value": "blue"}}
    rds.describe_db_instances.side_effect = [
        {"DBInstances": [{"DBInstanceStatus": "available", "Endpoint": {"Address": "green.rds", "Port": 5432}}]},
        {"DBInstances": [{"DBInstanceStatus": "available", "Endpoint": {"Address": "blue.rds", "Port": 5432}}]},
    ]

    monkeypatch.setattr(rbg.boto3, "client", lambda svc, **kw: rds if svc == "rds" else ssm)
    monkeypatch.setattr(rbg, "ROUTE53_ZONE_ID", "")
    monkeypatch.setattr(rbg, "RDS_ACTIVE_CNAME", "")

    args = argparse.Namespace(target=None, skip_health_check=True, dry_run=True, force=False)
    assert rbg.cmd_swap(args) == 0
    ssm.put_parameter.assert_not_called()


def test_swap_updates_ssm_and_refuses_unavailable_rds(monkeypatch):
    """Live swap updates both SSM params; refuses to swap if target RDS is modifying."""
    rds = MagicMock()
    ssm = MagicMock()
    ssm.exceptions.ParameterNotFound = KeyError
    ssm.get_parameter.return_value = {"Parameter": {"Value": "blue"}}

    # 1. Unavailable target should fail before mutating SSM
    rds.describe_db_instances.side_effect = [
        {"DBInstances": [{"DBInstanceStatus": "modifying", "Endpoint": {"Address": "green.rds", "Port": 5432}}]},
        {"DBInstances": [{"DBInstanceStatus": "available", "Endpoint": {"Address": "blue.rds", "Port": 5432}}]},
    ]
    monkeypatch.setattr(rbg.boto3, "client", lambda svc, **kw: rds if svc == "rds" else ssm)
    monkeypatch.setattr(rbg, "TEAMS_WEBHOOK_URL", "")
    monkeypatch.setattr(rbg, "ROUTE53_ZONE_ID", "")

    args = argparse.Namespace(target="green", skip_health_check=True, dry_run=False, force=False)
    with pytest.raises(RuntimeError, match="Cannot swap"):
        rbg.cmd_swap(args)
    ssm.put_parameter.assert_not_called()

    # 2. Available target updates both SSM color and host parameters
    rds.describe_db_instances.side_effect = [
        {"DBInstances": [{"DBInstanceStatus": "available", "Endpoint": {"Address": "green.rds", "Port": 5432}}]},
        {"DBInstances": [{"DBInstanceStatus": "available", "Endpoint": {"Address": "blue.rds", "Port": 5432}}]},
    ]
    assert rbg.cmd_swap(args) == 0
    assert ssm.put_parameter.call_count == 2
