"""Lightweight, high-speed PostGIS database layer replacing `datum` and `geopetl`.

Uses native PostgreSQL `COPY FROM STDIN` for bulk writes (10x-30x faster than
row-by-row INSERT statements) and supports all PostGIS geometry types, SRID
transforms, and table/index/view helpers needed by the AIS engine scripts.
"""

from __future__ import annotations

import csv
import io
import uuid
from typing import Any, Iterable

import psycopg2
from psycopg2.extras import RealDictCursor

from ais.util import parse_url, redact_url

FIELD_TYPE_MAP = {
    "smallint": "num",
    "bigint": "num",
    "integer": "num",
    "numeric": "num",
    "double precision": "num",
    "real": "num",
    "text": "text",
    "character varying": "text",
    "character": "text",
    "boolean": "bool",
    "date": "date",
    "timestamp without time zone": "date",
    "timestamp with time zone": "date",
    "USER-DEFINED": "geom",
    "name": "name",
    "bytea": "text",
}

CREATE_TYPE_MAP = {
    "text": "text",
    "num": "numeric",
    "integer": "integer",
    "float": "double precision",
    "date": "timestamp",
    "geom": "geometry",
}

_NULL_TOKEN = r"\N"


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _quote_table(schema: str, name: str) -> str:
    return f"{_quote_ident(schema)}.{_quote_ident(name)}"


def _split_table_name(full_name: str) -> tuple[str, str]:
    if "." in full_name:
        schema, name = full_name.split(".", 1)
        return schema.lower(), name.lower()
    return "public", full_name.lower()


class Table:
    """PostGIS table interface backed by psycopg2 + COPY."""

    def __init__(self, db: Database, full_name: str):
        self.db = db
        self.schema, self.name = _split_table_name(full_name)
        self._c = db._c
        self.metadata = self._get_metadata()
        self._type_by_field = {m["name"]: m["type"] for m in self.metadata}
        self._pg_type_by_field = {m["name"]: m["pg_type"] for m in self.metadata}
        self._geom_field = self._find_geom_field()
        self.geom_type = self._get_geom_type() if self._geom_field else None
        self.srid = self._get_srid() if self._geom_field else None

    def __str__(self) -> str:
        return f"Table: {self.schema}.{self.name}"

    @property
    def fields(self) -> list[str]:
        return [m["name"] for m in self.metadata]

    @property
    def geom_field(self) -> str | None:
        return self._geom_field

    def _get_metadata(self) -> list[dict[str, str]]:
        self._c.execute(
            """
            SELECT column_name AS name, data_type AS pg_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (self.schema, self.name),
        )
        rows = self._c.fetchall()
        return [
            {
                "name": r["name"],
                "type": FIELD_TYPE_MAP.get(r["pg_type"], "text"),
                "pg_type": r["pg_type"],
            }
            for r in rows
        ]

    def _find_geom_field(self) -> str | None:
        geom_cols = [m["name"] for m in self.metadata if m["type"] == "geom"]
        if not geom_cols:
            return None
        if len(geom_cols) > 1:
            raise LookupError(f"Multiple geometry fields on {self.schema}.{self.name}: {geom_cols}")
        return geom_cols[0]

    def _get_srid(self) -> int:
        self._c.execute(
            "SELECT Find_SRID(%s, %s, %s) AS srid",
            (self.schema, self.name, self._geom_field),
        )
        row = self._c.fetchone()
        return int(row["srid"]) if row and row["srid"] else 2272

    def _get_geom_type(self) -> str | None:
        self._c.execute(
            """
            SELECT type
            FROM geometry_columns
            WHERE f_table_schema = %s
              AND f_table_name = %s
              AND f_geometry_column = %s
            """,
            (self.schema, self.name, self._geom_field),
        )
        row = self._c.fetchone()
        return row["type"] if row else None

    def _wkt_getter(self, geom_field: str, to_srid: int | None = None) -> str:
        col = _quote_ident(geom_field)
        expr = f"ST_Transform({col}, {int(to_srid)})" if to_srid else col
        return f"ST_AsText({expr}) AS {col}"

    def read(
        self,
        fields: list[str] | None = None,
        aliases: dict[str, str] | None = None,
        geom_field: str | None = None,
        return_geom: bool = True,
        to_srid: int | None = None,
        limit: int | None = None,
        where: str | None = None,
        sort: str | list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Read rows as dicts, converting geometry columns to WKT when requested."""
        fq_table = _quote_table(self.schema, self.name)
        gfield = geom_field or self._geom_field

        if fields:
            select_parts = []
            has_geom_in_fields = False
            for f in fields:
                if gfield and f == gfield:
                    has_geom_in_fields = True
                    if return_geom:
                        alias = aliases.get(f) if aliases else None
                        col = _quote_ident(f)
                        expr = f"ST_Transform({col}, {int(to_srid)})" if to_srid else col
                        out_name = _quote_ident(alias) if alias else col
                        select_parts.append(f"ST_AsText({expr}) AS {out_name}")
                    continue
                if aliases and f in aliases:
                    select_parts.append(f"{_quote_ident(f)} AS {_quote_ident(aliases[f])}")
                else:
                    select_parts.append(_quote_ident(f))
            if gfield and return_geom and not has_geom_in_fields:
                select_parts.append(self._wkt_getter(gfield, to_srid=to_srid))
            stmt = f"SELECT {', '.join(select_parts)} FROM {fq_table}"
        else:
            if gfield and return_geom:
                non_geom = [_quote_ident(f) for f in self.fields if f != gfield]
                non_geom.append(self._wkt_getter(gfield, to_srid=to_srid))
                stmt = f"SELECT {', '.join(non_geom)} FROM {fq_table}"
            else:
                stmt = f"SELECT * FROM {fq_table}"

        if where:
            stmt += f" WHERE {where}"
        if sort:
            order_clause = ", ".join(sort) if isinstance(sort, (list, tuple)) else sort
            stmt += f" ORDER BY {order_clause}"
        if limit:
            stmt += f" LIMIT {int(limit)}"

        self._c.execute(stmt)
        return self._c.fetchall()

    def delete(self, cascade: bool = False) -> None:
        """Truncate all rows and reset identity sequences."""
        fq_table = _quote_table(self.schema, self.name)
        stmt = f"TRUNCATE {fq_table} RESTART IDENTITY"
        if cascade:
            stmt += " CASCADE"
        self._c.execute(stmt)
        self.db.save()

    def write(
        self,
        rows: list[dict[str, Any]],
        from_srid: int | None = None,
        chunk_size: int = 150000,
    ) -> None:
        """Bulk-insert rows using PostgreSQL COPY FROM STDIN."""
        if not rows:
            return

        fields = list(rows[0].keys())
        for f in fields:
            if f not in self._type_by_field:
                raise ValueError(f"Field `{f}` does not exist on {self.schema}.{self.name}")

        gfield = self._geom_field if (self._geom_field in fields) else None
        srid = int(from_srid or self.srid or 2272)
        needs_multi = bool(gfield and self.geom_type and self.geom_type.upper().startswith("MULTI"))
        fq_table = _quote_table(self.schema, self.name)
        cols_sql = ", ".join(_quote_ident(f) for f in fields)

        # Determine if we can COPY directly or should normalize geometries via a TEMP table.
        # Non-geom tables and simple POINT/LINESTRING tables copy directly at maximum speed;
        # MULTI* geometry tables or geometries containing CURVE/NaN use a temp staging table
        # so PostGIS handles ST_Multi / ST_Force2D / ST_CurveToLine in a single set operation.
        use_geom_staging = False
        if gfield:
            if needs_multi:
                use_geom_staging = True
            else:
                for row in rows:
                    g = row.get(gfield)
                    if g and ("CURVE" in g or "CIRC" in g or "NaN" in g):
                        use_geom_staging = True
                        break

        if not use_geom_staging:
            self._copy_chunks(fq_table, cols_sql, fields, rows, gfield, srid, chunk_size)
            self.db.save()
            return

        # Staging path for MULTI* / 3D / curved geometries
        tmp_name = f"tmp_copy_{uuid.uuid4().hex[:12]}"
        col_defs = []
        select_exprs = []
        for f in fields:
            qf = _quote_ident(f)
            if f == gfield:
                col_defs.append(f"{qf} text")
                geom_expr = f"ST_GeomFromText(replace({qf}, 'NaN', '0'), {srid})"
                geom_expr = f"ST_Force2D({geom_expr})"
                geom_expr = f"CASE WHEN {qf} LIKE '%CURVE%' OR {qf} LIKE 'CIRC%' THEN ST_CurveToLine({geom_expr}) ELSE {geom_expr} END"
                if needs_multi:
                    geom_expr = f"ST_Multi({geom_expr})"
                select_exprs.append(f"CASE WHEN {qf} IS NULL OR {qf} = '' THEN NULL ELSE {geom_expr} END")
            else:
                pg_type = self._pg_type_by_field.get(f, "text")
                if pg_type == "USER-DEFINED":
                    pg_type = "text"
                col_defs.append(f"{qf} {pg_type}")
                select_exprs.append(qf)

        self._c.execute(f"CREATE TEMP TABLE {tmp_name} ({', '.join(col_defs)}) ON COMMIT DROP")
        self._copy_chunks(tmp_name, cols_sql, fields, rows, gfield=None, srid=srid, chunk_size=chunk_size, raw_geom_field=gfield)
        self._c.execute(
            f"INSERT INTO {fq_table} ({cols_sql}) SELECT {', '.join(select_exprs)} FROM {tmp_name}"
        )
        self.db.save()

    def _copy_chunks(
        self,
        target_sql: str,
        cols_sql: str,
        fields: list[str],
        rows: list[dict[str, Any]],
        gfield: str | None,
        srid: int,
        chunk_size: int,
        raw_geom_field: str | None = None,
    ) -> None:
        copy_sql = f"COPY {target_sql} ({cols_sql}) FROM STDIN WITH (FORMAT csv, NULL '{_NULL_TOKEN}')"
        field_specs = [
            (f, self._type_by_field[f], self._pg_type_by_field.get(f, ""))
            for f in fields
        ]
        int_types = ("smallint", "integer", "bigint")
        total = len(rows)
        step = chunk_size or total

        for start in range(0, total, step):
            buf = io.StringIO()
            writer = csv.writer(buf, lineterminator="\n")
            for row in rows[start : start + step]:
                out_row = []
                for f, ftype, pg_type in field_specs:
                    val = row.get(f)
                    if f == gfield:
                        if not val:
                            out_row.append(_NULL_TOKEN)
                        elif str(val).startswith("SRID="):
                            out_row.append(str(val))
                        else:
                            out_row.append(f"SRID={srid};{val}")
                    elif f == raw_geom_field:
                        out_row.append(_NULL_TOKEN if not val else str(val))
                    elif ftype == "text":
                        out_row.append("" if val is None else str(val))
                    elif ftype == "num":
                        if val is None or val == "":
                            out_row.append(_NULL_TOKEN)
                        elif pg_type in int_types:
                            out_row.append(int(val) if not isinstance(val, str) else int(float(val)))
                        else:
                            out_row.append(val)
                    else:
                        out_row.append(_NULL_TOKEN if val is None else val)
                writer.writerow(out_row)
            buf.seek(0)
            self._c.copy_expert(copy_sql, buf)

    def _index_name(self, fields: tuple[str, ...]) -> str:
        return "_".join([self.name, *fields, "idx"])

    def create_index(self, *fields: str, name: str | None = None) -> None:
        idx_name = name or self._index_name(fields)
        cols = ", ".join(_quote_ident(f) for f in fields)
        fq_table = _quote_table(self.schema, self.name)
        self._c.execute(f"CREATE INDEX IF NOT EXISTS {_quote_ident(idx_name)} ON {fq_table} ({cols})")
        self.db.save()

    def drop_index(self, *fields: str, name: str | None = None) -> None:
        idx_name = name or self._index_name(fields)
        self._c.execute(f"DROP INDEX IF EXISTS {_quote_ident(self.schema)}.{_quote_ident(idx_name)}")
        self.db.save()


class Database:
    """PostgreSQL / PostGIS database connection wrapper."""

    def __init__(self, url: str):
        parsed = parse_url(url)
        # Never retain raw credentials on the instance (prevents leaks in logs/tracebacks)
        self.safe_url = redact_url(url)
        self.conn = psycopg2.connect(
            host=parsed["host"] or "localhost",
            port=parsed["port"] or 5432,
            user=parsed["user"],
            password=parsed["password"],
            dbname=parsed["db_name"],
        )
        self._c = self.conn.cursor(cursor_factory=RealDictCursor)

    def __repr__(self) -> str:
        return f"Database({self.safe_url!r})"

    __str__ = __repr__

    def __getitem__(self, table_name: str) -> Table:
        return Table(self, table_name)

    def execute(self, stmt: str, params: Any = None) -> list[dict[str, Any]] | None:
        self._c.execute(stmt, params)
        if self._c.description is not None:
            return self._c.fetchall()
        return None

    def save(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        try:
            self._c.close()
        finally:
            self.conn.close()

    def create_table(self, table_name: str, fields: list[dict[str, str]]) -> None:
        schema, name = _split_table_name(table_name)
        fq_table = _quote_table(schema, name)
        col_defs = [
            f"{_quote_ident(f['name'])} {CREATE_TYPE_MAP.get(f['type'], f['type'])}"
            for f in fields
        ]
        self._c.execute(f"CREATE TABLE {fq_table} ({', '.join(col_defs)})")
        self.save()

    def drop_table(self, table_name: str) -> None:
        schema, name = _split_table_name(table_name)
        fq_table = _quote_table(schema, name)
        self._c.execute(f"DROP TABLE IF EXISTS {fq_table}")
        self.save()

    def create_view(self, view_name: str, select_stmt: str) -> None:
        schema, name = _split_table_name(view_name)
        fq_view = _quote_table(schema, name)
        self._c.execute(f"CREATE OR REPLACE VIEW {fq_view} AS {select_stmt}")
        self.save()

    def drop_view(self, view_name: str) -> None:
        schema, name = _split_table_name(view_name)
        fq_view = _quote_table(schema, name)
        self._c.execute(f"DROP VIEW IF EXISTS {fq_view} CASCADE")
        self.save()


def connect(url: str) -> Database:
    """Open a PostGIS Database connection."""
    return Database(url)


def copy_rows_to_table(
    conn,
    table_name: str,
    columns: list[str],
    rows: Iterable[tuple[Any, ...]],
    truncate: bool = True,
) -> int:
    """Stream an iterable of row tuples into a PostgreSQL table via COPY FROM STDIN."""
    cols_sql = ", ".join(_quote_ident(c) for c in columns)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    count = 0
    for row in rows:
        writer.writerow([_NULL_TOKEN if v is None else v for v in row])
        count += 1
    buf.seek(0)

    with conn.cursor() as cur:
        if truncate:
            cur.execute(f"DELETE FROM {table_name}")
        cur.copy_expert(
            f"COPY {table_name} ({cols_sql}) FROM STDIN WITH (FORMAT csv, NULL '{_NULL_TOKEN}')",
            buf,
        )
    conn.commit()
    return count
