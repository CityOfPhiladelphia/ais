"""Unit tests for unified configuration, data source definitions, and preprocessors."""

import ais.config as cfg
from ais.config.sources import (
    ADDRESSES,
    BASE_DATA_SOURCES,
    make_dor_parcel_id,
    make_eclipse_address,
    make_pwd_account_address,
    make_rtt_address,
    make_voter_address,
    make_voter_name,
)


def test_sqlalchemy_uri_uses_psycopg2_driver():
    """SQLAlchemy 2.1 defaults postgresql:// to psycopg v3; AIS must explicitly specify psycopg2."""
    assert cfg.SQLALCHEMY_DATABASE_URI.startswith("postgresql+psycopg2://")


def test_settings_masks_secrets_by_default():
    """AISSettings wraps passwords and DB URLs in SecretStr so repr/str never leaks them."""
    s = cfg.AISSettings(
        _env_file=None,
        engine_db_host="db.example.com",
        engine_db_pass="SuperSecretEnginePass",
        citygeo_db_url="postgresql://citygeo:SuperSecretCityGeo@db.example.com:5432/databridge",
        airflow_trigger_pass="SuperSecretAirflow",
    )
    rendered = f"{s!r} {s.databases!r} {s.blue_database!r} {s.airflow_trigger_creds!r}"
    assert "SuperSecretEnginePass" not in rendered
    assert "SuperSecretCityGeo" not in rendered
    assert "SuperSecretAirflow" not in rendered
    assert s.effective_sqlalchemy_uri == "postgresql+psycopg2://ais_engine:SuperSecretEnginePass@db.example.com:5432/ais_engine"


def test_no_oracle_sources_in_config():
    """All engine build sources must use Databridge (`citygeo`) or local `engine` — never Oracle."""
    allowed_dbs = {"citygeo", "engine"}

    for name, src in BASE_DATA_SOURCES.items():
        if "db" in src:
            assert src["db"] in allowed_dbs, f"BASE_DATA_SOURCES[{name!r}] uses {src['db']!r}"
        else:
            for sub_name, sub_src in src.items():
                assert sub_src["db"] in allowed_dbs, f"BASE_DATA_SOURCES[{name!r}][{sub_name!r}] uses {sub_src['db']!r}"

    for src in ADDRESSES["sources"]:
        assert src["db"] in allowed_dbs, f"ADDRESSES source {src['name']!r} uses {src['db']!r}"

    for layer in cfg.SERVICE_AREAS["layers"]:
        for stype, src in layer["sources"].items():
            assert src["db"] in allowed_dbs, f"Service area {layer['layer_id']!r}/{stype} uses {src['db']!r}"


def test_pwd_accounts_uses_databridge_viewer_pwd_accounts():
    """Verify pwd_accounts reads one_address and water_account from viewer_pwd.accounts."""
    pwd_src = next(s for s in ADDRESSES["sources"] if s["name"] == "pwd_accounts")
    assert pwd_src["db"] == "citygeo"
    assert pwd_src["table"] == "viewer_pwd.accounts"
    assert pwd_src["address_fields"] == {"street_address": "one_address"}
    assert pwd_src["tag_fields"][0]["source_fields"] == ["water_account"]


def test_service_area_layer_ids_are_unique():
    """Duplicate service area layer_ids would break CREATE TABLE service_area_summary."""
    layer_ids = [layer["layer_id"] for layer in cfg.SERVICE_AREAS["layers"]]
    assert len(layer_ids) == len(set(layer_ids))


def test_make_pwd_account_address():
    """Normalizes -R/-REAR suffixes and handles null/empty inputs safely."""
    assert make_pwd_account_address({"street_address": "1234-REAR MARKET ST"}) == "1234R MARKET ST"
    assert make_pwd_account_address({"street_address": "1234-R MARKET ST"}) == "1234R MARKET ST"
    assert make_pwd_account_address({"street_address": "1800 GEARY ST"}) == "1800 GEARY ST"
    assert make_pwd_account_address({"street_address": None}) is None
    assert make_pwd_account_address({"street_address": ""}) is None


def test_address_preprocessors():
    """Verify voter, DOR parcel ID, Eclipse, and RTT preprocessors."""
    assert make_voter_address({
        "address_low": "1234",
        "address_low_suffix": None,
        "street_name": "MARKET ST",
        "unit_num": "2A",
    }) == "1234 MARKET ST # 2A"
    assert make_voter_address({
        "address_low": "1234",
        "address_low_suffix": None,
        "street_name": "MARKET ST",
        "unit_num": "APT 2A",
    }) == "1234 MARKET ST APT 2A"
    assert make_voter_name({"first_name": "JANE", "middle_name": None, "last_name": "DOE"}) == "JANE DOE"
    assert make_dor_parcel_id({"reg_map_id": "009-S-19-0092"}) == "009S190092"
    assert make_eclipse_address({"base_address": "100 MAIN ST", "unit_type": None, "unit_num": "5"}) == "100 MAIN ST # 5"
    assert make_eclipse_address({"base_address": None, "unit_type": "APT", "unit_num": "5"}) is None
    assert make_rtt_address({
        "address_low": 100,
        "address_low_suffix": None,
        "address_high": "0102",
        "unit_num": None,
        "street_predir": "N",
        "street_name": "BROAD",
        "street_type": "ST",
        "street_postdir": None,
    }) == "100-102 N BROAD ST"
