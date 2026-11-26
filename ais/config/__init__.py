"""Unified, type-validated AIS configuration powered by pydantic-settings & SecretStr."""

from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from ais.config.service_areas import SERVICE_AREAS
from ais.config.sources import (
    ADDRESS_SUMMARY,
    ADDRESSES,
    BASE_DATA_SOURCES,
    GEOCODE,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _import_passyunk_parser():
    """Import PassyunkParser without hitting GitHub's unauthenticated API on startup.

    Upstream `passyunk.parser` calls `check_version()` at import time, which
    fetches tags from `api.github.com` and raises `UnboundLocalError` whenever
    GitHub is unreachable or rate-limited (60 req/hr per NAT IP in EKS).
    """
    import requests

    orig_get = requests.get

    class _NoopResponse:
        def json(self):
            return [
                {"object": {"type": "tag"}, "ref": "refs/tags/0.0.0"},
                {"object": {"type": "tag"}, "ref": "refs/tags/0.0.0+private"},
            ]

    def _guarded_get(url, *args, **kwargs):
        if "api.github.com/repos/CityOfPhiladelphia/passyunk" in str(url):
            return _NoopResponse()
        return orig_get(url, *args, **kwargs)

    requests.get = _guarded_get
    try:
        from passyunk.parser import PassyunkParser

        return PassyunkParser
    finally:
        requests.get = orig_get


PassyunkParser = _import_passyunk_parser()


def _build_pg_uri(
    host: str,
    password: str,
    user: str = "ais_engine",
    port: int = 5432,
    dbname: str = "ais_engine",
    scheme: str = "postgresql+psycopg2",
) -> str:
    return f"{scheme}://{user}:{password}@{host}:{port}/{dbname}"


class AISSettings(BaseSettings):
    """Typed environment settings; all passwords and DB URLs use SecretStr."""

    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- API Runtime ---------------------------------------------------------
    debug: bool = False
    profile: bool = False
    sentry_dsn: SecretStr | None = None

    engine_db_host: str = "localhost"
    engine_db_port: int = 5432
    engine_db_user: str = "ais_engine"
    engine_db_name: str = "ais_engine"
    engine_db_pass: SecretStr = SecretStr("")

    sqlalchemy_database_uri: SecretStr | None = None
    sqlalchemy_echo: bool = False
    sqlalchemy_pool_size: int | None = None

    # --- Engine Build Server -------------------------------------------------
    local_engine_db_host: str = "localhost"
    local_engine_db_user: str = "ais_engine"
    local_engine_db_pass: SecretStr = SecretStr("")
    local_engine_db_name: str = "ais_engine"
    engine_build_db_url: SecretStr | None = None

    citygeo_db_url: SecretStr | None = None
    ng911_transform_db_url: SecretStr | None = None

    # --- RDS Blue-Green ------------------------------------------------------
    rds_engine_db_user: str = "ais_engine"
    rds_engine_db_name: str = "ais_engine"
    rds_engine_db_pass: SecretStr = SecretStr("")
    blue_rds_host: str = "ais-engine-blue.cfuoybzycpox.us-east-1.rds.amazonaws.com"
    green_rds_host: str = "ais-engine-green.cfuoybzycpox.us-east-1.rds.amazonaws.com"

    # --- Notifications & Airflow ---------------------------------------------
    teams_webhook_url: SecretStr | None = None
    airflow_trigger_url: str = ""
    airflow_trigger_user: str = ""
    airflow_trigger_pass: SecretStr = SecretStr("")

    @property
    def effective_engine_pass(self) -> SecretStr:
        if self.engine_db_pass.get_secret_value():
            return self.engine_db_pass
        return self.local_engine_db_pass

    @property
    def effective_sqlalchemy_uri(self) -> str:
        if self.sqlalchemy_database_uri and self.sqlalchemy_database_uri.get_secret_value():
            return self.sqlalchemy_database_uri.get_secret_value()
        return _build_pg_uri(
            host=self.engine_db_host,
            password=self.effective_engine_pass.get_secret_value(),
            user=self.engine_db_user,
            port=self.engine_db_port,
            dbname=self.engine_db_name,
            scheme="postgresql+psycopg2",
        )

    @property
    def local_build_database(self) -> dict[str, str | SecretStr]:
        pw = self.local_engine_db_pass if self.local_engine_db_pass.get_secret_value() else self.effective_engine_pass
        return {
            "user": self.local_engine_db_user,
            "host": self.local_engine_db_host,
            "password": pw,
            "dbname": self.local_engine_db_name,
        }

    @property
    def blue_database(self) -> dict[str, str | SecretStr]:
        pw = self.rds_engine_db_pass if self.rds_engine_db_pass.get_secret_value() else self.effective_engine_pass
        return {
            "user": self.rds_engine_db_user,
            "host": self.blue_rds_host,
            "password": pw,
            "dbname": self.rds_engine_db_name,
        }

    @property
    def green_database(self) -> dict[str, str | SecretStr]:
        pw = self.rds_engine_db_pass if self.rds_engine_db_pass.get_secret_value() else self.effective_engine_pass
        return {
            "user": self.rds_engine_db_user,
            "host": self.green_rds_host,
            "password": pw,
            "dbname": self.rds_engine_db_name,
        }

    @property
    def databases(self) -> dict[str, SecretStr]:
        """Return DB URLs wrapped in SecretStr so printing/logging never leaks passwords."""
        if self.engine_build_db_url and self.engine_build_db_url.get_secret_value():
            engine_url = self.engine_build_db_url
        else:
            local = self.local_build_database
            local_pw = local["password"]
            raw_pw = local_pw.get_secret_value() if isinstance(local_pw, SecretStr) else str(local_pw)
            engine_url = SecretStr(
                _build_pg_uri(
                    host=str(local["host"]),
                    password=raw_pw,
                    user=str(local["user"]),
                    port=self.engine_db_port,
                    dbname=str(local["dbname"]),
                    scheme="postgresql",
                )
            )

        dbs: dict[str, SecretStr] = {"engine": engine_url}
        if self.citygeo_db_url and self.citygeo_db_url.get_secret_value():
            dbs["citygeo"] = self.citygeo_db_url
        if self.ng911_transform_db_url and self.ng911_transform_db_url.get_secret_value():
            dbs["ng911_transform"] = self.ng911_transform_db_url
        return dbs

    @property
    def airflow_trigger_creds(self) -> dict[str, str | SecretStr]:
        return {
            "url": self.airflow_trigger_url,
            "user": self.airflow_trigger_user,
            "pw": self.airflow_trigger_pass,
        }


settings = AISSettings()

# ---------------------------------------------------------------------------
# Flask & engine configuration exports (consumed by `app.config.from_object`)
# ---------------------------------------------------------------------------
DEBUG = settings.debug
PROFILE = settings.profile
SENTRY_DSN = settings.sentry_dsn.get_secret_value() if settings.sentry_dsn else None

ENGINE_DB_HOST = settings.engine_db_host
ENGINE_DB_PORT = settings.engine_db_port
ENGINE_DB_USER = settings.engine_db_user
ENGINE_DB_NAME = settings.engine_db_name
ENGINE_DB_PASS = settings.effective_engine_pass

SQLALCHEMY_DATABASE_URI = settings.effective_sqlalchemy_uri
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ECHO = settings.sqlalchemy_echo
if settings.sqlalchemy_pool_size is not None:
    SQLALCHEMY_POOL_SIZE = settings.sqlalchemy_pool_size

PARSER = PassyunkParser
ENGINE_SRID = 2272
DEFAULT_API_SRID = 4326
DEFAULT_SEARCH_RADIUS = 300
MAXIMUM_SEARCH_RADIUS = 10000
DEFAULT_AIS_MAX_RANGE = 0
OWNER_RESPONSE_LIMIT = 999
OWNER_PARTS_THRESHOLD = 10
VALID_ADDRESS_LOW_SUFFIXES = ("F", "R", "A", "S", "M", "P", "G", "B", "C", "D", "L", "Q", "2")

LOCAL_BUILD_DATABASE = settings.local_build_database
BLUE_DATABASE = settings.blue_database
GREEN_DATABASE = settings.green_database
DATABASES = settings.databases
AIRFLOW_TRIGGER_CREDS = settings.airflow_trigger_creds

__all__ = [
    "ADDRESSES",
    "ADDRESS_SUMMARY",
    "AIRFLOW_TRIGGER_CREDS",
    "AISSettings",
    "BASE_DATA_SOURCES",
    "BLUE_DATABASE",
    "DATABASES",
    "DEBUG",
    "DEFAULT_AIS_MAX_RANGE",
    "DEFAULT_API_SRID",
    "DEFAULT_SEARCH_RADIUS",
    "ENGINE_DB_HOST",
    "ENGINE_DB_NAME",
    "ENGINE_DB_PASS",
    "ENGINE_DB_PORT",
    "ENGINE_DB_USER",
    "ENGINE_SRID",
    "GEOCODE",
    "GREEN_DATABASE",
    "LOCAL_BUILD_DATABASE",
    "MAXIMUM_SEARCH_RADIUS",
    "OWNER_PARTS_THRESHOLD",
    "OWNER_RESPONSE_LIMIT",
    "PARSER",
    "PROFILE",
    "SENTRY_DSN",
    "SERVICE_AREAS",
    "SQLALCHEMY_DATABASE_URI",
    "SQLALCHEMY_ECHO",
    "SQLALCHEMY_TRACK_MODIFICATIONS",
    "VALID_ADDRESS_LOW_SUFFIXES",
    "settings",
]
