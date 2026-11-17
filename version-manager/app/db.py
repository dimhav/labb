"""Lasning av data ur warehouse-databasen (for portalen)."""
from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

# Scheman som visas i portalen (i denna ordning).
VISIBLE_SCHEMAS = ("raw", "analytics")


def _conn_params() -> dict:
    return {
        "host": os.environ.get("POSTGRES_HOST", "postgres"),
        "port": int(os.environ.get("POSTGRES_PORT", "5432")),
        "user": os.environ.get("POSTGRES_USER", "warehouse"),
        "password": os.environ.get("POSTGRES_PASSWORD", "warehouse"),
        "dbname": os.environ.get("POSTGRES_DB", "warehouse"),
    }


@contextmanager
def _cursor():
    conn = psycopg2.connect(connect_timeout=5, **_conn_params())
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
    finally:
        conn.close()


def _quote_ident(name: str) -> str:
    """Sakerstaller att ett identifierarnamn ar ofarligt (undviker SQL-injektion)."""
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Ogiltigt identifierarnamn: {name!r}")
    return '"' + name + '"'


def list_tables() -> list[dict]:
    """Returnerar tabeller i de synliga schemana med radantal."""
    with _cursor() as cur:
        cur.execute(
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = ANY(%s)
              AND table_type IN ('BASE TABLE', 'VIEW')
            ORDER BY table_schema, table_name
            """,
            (list(VISIBLE_SCHEMAS),),
        )
        tables = [dict(r) for r in cur.fetchall()]

        # Riktigt radantal (datasetet ar litet nog for exakta tal).
        for t in tables:
            cur.execute(
                f'SELECT count(*) AS n FROM {_quote_ident(t["table_schema"])}.'
                f'{_quote_ident(t["table_name"])}'
            )
            t["rows"] = int(cur.fetchone()["n"])
    return tables


def table_columns(schema: str, table: str) -> list[dict]:
    with _cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, table),
        )
        return [dict(r) for r in cur.fetchall()]


def preview_table(schema: str, table: str, limit: int = 25) -> dict:
    """Returnerar kolumner och de forsta raderna i en tabell."""
    if schema not in VISIBLE_SCHEMAS:
        raise ValueError(f"Schemat {schema!r} ar inte synligt")
    limit = max(1, min(limit, 200))
    cols = table_columns(schema, table)
    if not cols:
        raise ValueError(f"Tabellen {schema}.{table} finns inte")

    sql = f"SELECT * FROM {_quote_ident(schema)}.{_quote_ident(table)} LIMIT %s"
    with _cursor() as cur:
        cur.execute(sql, (limit,))
        rows = cur.fetchall()

    out_rows = []
    for row in rows:
        out_rows.append(
            {k: (str(v) if v is not None else None) for k, v in row.items()}
        )
    return {
        "schema": schema,
        "table": table,
        "columns": [c["column_name"] for c in cols],
        "column_types": {c["column_name"]: c["data_type"] for c in cols},
        "rows": out_rows,
    }


def warehouse_stats() -> dict:
    """Sammanfattande siffror for portalen."""
    with _cursor() as cur:
        cur.execute("SELECT version() AS v")
        version = cur.fetchone()["v"].split(" ")[1]

        cur.execute(
            """
            SELECT table_schema, count(*) AS n
            FROM information_schema.tables
            WHERE table_schema = ANY(%s)
              AND table_type IN ('BASE TABLE', 'VIEW')
            GROUP BY table_schema
            """,
            (list(VISIBLE_SCHEMAS),),
        )
        table_counts = {r["table_schema"]: r["n"] for r in cur.fetchall()}

        rows_by_schema = {}
        for schema in VISIBLE_SCHEMAS:
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = %s AND table_type IN ('BASE TABLE', 'VIEW')
                """,
                (schema,),
            )
            total = 0
            for row in cur.fetchall():
                cur.execute(
                    f'SELECT count(*) AS n FROM {_quote_ident(schema)}.'
                    f'{_quote_ident(row["table_name"])}'
                )
                total += int(cur.fetchone()["n"])
            rows_by_schema[schema] = total

    return {
        "server_version": version,
        "schemas": list(VISIBLE_SCHEMAS),
        "table_counts": table_counts,
        "rows_by_schema": rows_by_schema,
    }
