"""Unit tests for the native psycopg2/COPY PostGIS layer in `ais.engine.db`."""

from decimal import Decimal
from unittest.mock import MagicMock
from pydantic import SecretStr

from ais.engine.db import Database, Table, _quote_ident, _split_table_name, copy_rows_to_table
from ais.util import redact_url


def test_database_repr_never_exposes_password(monkeypatch):
    """Database accepts SecretStr/str and retains only a redacted URL."""
    monkeypatch.setattr("ais.engine.db.psycopg2.connect", lambda **kw: MagicMock())
    db = Database(SecretStr("postgis://citygeo:TopSecret123@db.internal:5432/databridge"))
    assert not hasattr(db, "url")
    assert "TopSecret123" not in repr(db)
    assert "TopSecret123" not in str(db)
    assert db.safe_url == redact_url("postgis://citygeo:TopSecret123@db.internal:5432/databridge")


def _make_mock_table(metadata, geom_field=None, srid=2272):
    """Construct a Table instance with a mocked cursor so COPY buffers can be inspected."""
    tbl = Table.__new__(Table)
    tbl.schema = "public"
    tbl.name = "test_table"
    tbl.metadata = metadata
    tbl._type_by_field = {m["name"]: m["type"] for m in metadata}
    tbl._pg_type_by_field = {m["name"]: m["pg_type"] for m in metadata}
    tbl._geom_field = geom_field
    tbl.geom_type = "POINT" if geom_field else None
    tbl.srid = srid if geom_field else None

    captured = []

    def fake_copy_expert(sql, buf):
        captured.append((sql, buf.read()))

    cursor = MagicMock()
    cursor.copy_expert.side_effect = fake_copy_expert
    tbl._c = cursor
    tbl.db = MagicMock()
    return tbl, captured


def test_identifier_and_table_splitting():
    """Verify schema.table splitting and identifier quoting."""
    assert _split_table_name("viewer_pwd.accounts") == ("viewer_pwd", "accounts")
    assert _split_table_name("Address_Summary") == ("public", "address_summary")
    assert _quote_ident('a"b') == '"a""b"'


def test_copy_chunks_coerces_decimal_to_integer_and_handles_nulls():
    """Regression test: ESRI NUMERIC/Decimal values must be formatted as ints for integer columns."""
    tbl, captured = _make_mock_table([
        {"name": "seg_id", "type": "num", "pg_type": "integer"},
        {"name": "street_name", "type": "text", "pg_type": "text"},
        {"name": "score", "type": "num", "pg_type": "double precision"},
    ])

    rows = [
        {"seg_id": Decimal("120045.000000"), "street_name": "MARKET", "score": 1.5},
        {"seg_id": "42.0", "street_name": None, "score": None},
        {"seg_id": None, "street_name": "BROAD, ST", "score": ""},
    ]
    tbl._copy_chunks(
        '"public"."test_table"',
        '"seg_id", "street_name", "score"',
        ["seg_id", "street_name", "score"],
        rows,
        gfield=None,
        srid=2272,
        chunk_size=10,
    )

    assert len(captured) == 1
    _, csv_body = captured[0]
    lines = csv_body.splitlines()
    assert lines[0] == "120045,MARKET,1.5"
    assert lines[1] == r"42,,\N"
    assert lines[2] == r'\N,"BROAD, ST",\N'


def test_copy_chunks_adds_ewkt_srid_prefix():
    """Plain WKT gets an SRID prefix; existing EWKT and nulls are preserved."""
    tbl, captured = _make_mock_table(
        [
            {"name": "street_address", "type": "text", "pg_type": "text"},
            {"name": "geom", "type": "geom", "pg_type": "USER-DEFINED"},
        ],
        geom_field="geom",
        srid=2272,
    )

    rows = [
        {"street_address": "1234 MARKET ST", "geom": "POINT (100 200)"},
        {"street_address": "1236 MARKET ST", "geom": "SRID=2272;POINT (300 400)"},
        {"street_address": "1238 MARKET ST", "geom": None},
    ]
    tbl._copy_chunks(
        '"public"."test_table"',
        '"street_address", "geom"',
        ["street_address", "geom"],
        rows,
        gfield="geom",
        srid=2272,
        chunk_size=10,
    )

    _, csv_body = captured[0]
    assert csv_body.splitlines() == [
        "1234 MARKET ST,SRID=2272;POINT (100 200)",
        "1236 MARKET ST,SRID=2272;POINT (300 400)",
        r"1238 MARKET ST,\N",
    ]


def test_copy_rows_to_table_streams_csv_and_commits():
    """copy_rows_to_table deletes existing rows when truncate=True and streams CSV via COPY."""
    captured = {}

    def fake_copy(sql, buf):
        captured["sql"] = sql
        captured["body"] = buf.read()

    cur = MagicMock()
    cur.copy_expert.side_effect = fake_copy
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur

    count = copy_rows_to_table(conn, "citygeo.true_range", ["seg_id", "val"], [(1, "A"), (2, None)], truncate=True)
    assert count == 2
    cur.execute.assert_called_once_with("DELETE FROM citygeo.true_range")
    assert "COPY citygeo.true_range" in captured["sql"]
    assert captured["body"].splitlines() == ["1,A", r"2,\N"]
    conn.commit.assert_called_once()
