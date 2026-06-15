"""
PostgreSQL provider using asyncpg directly for maximum streaming performance.
psycopg2 is used only for synchronous test_connection; asyncpg is used
everywhere else so we never block the event loop.
"""

import time
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
from asyncpg import Connection as AsyncpgConn

from app.providers.base_provider import BaseDatabaseProvider
from app.schemas.migration import ColumnSchema, TableSchema
from app.utils.logger import get_logger

logger = get_logger(__name__)

_PG_TYPE_MAP: dict[str, str] = {
    "int2": "SMALLINT",
    "int4": "INTEGER",
    "int8": "BIGINT",
    "float4": "FLOAT",
    "float8": "DOUBLE PRECISION",
    "numeric": "NUMERIC",
    "bool": "BOOLEAN",
    "text": "TEXT",
    "varchar": "VARCHAR",
    "bpchar": "CHAR",
    "bytea": "BYTEA",
    "date": "DATE",
    "time": "TIME",
    "timetz": "TIMETZ",
    "timestamp": "TIMESTAMP",
    "timestamptz": "TIMESTAMPTZ",
    "interval": "INTERVAL",
    "uuid": "UUID",
    "json": "JSON",
    "jsonb": "JSONB",
    "array": "TEXT",
}


def _build_dsn(credentials: dict) -> str:
    if "database_url" in credentials and credentials["database_url"]:
        url = credentials["database_url"]
        # asyncpg wants postgresql:// not postgres://
        return url.replace("postgres://", "postgresql://", 1)
    return (
        f"postgresql://{credentials['username']}:{credentials['password']}"
        f"@{credentials['host']}:{credentials.get('port', 5432)}"
        f"/{credentials['database']}"
    )


class PostgresProvider(BaseDatabaseProvider):
    def __init__(self, credentials: dict) -> None:
        self._dsn = _build_dsn(credentials)
        self._pool: asyncpg.Pool | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            self._dsn,
            min_size=1,
            max_size=5,
            command_timeout=60,
        )

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def test_connection(self) -> tuple[bool, str, float]:
        start = time.monotonic()
        try:
            conn: AsyncpgConn = await asyncpg.connect(self._dsn, timeout=10)
            await conn.execute("SELECT 1")
            await conn.close()
            latency = (time.monotonic() - start) * 1000
            return True, "Connection successful", round(latency, 2)
        except Exception as exc:
            return False, str(exc), 0.0

    # ── Schema discovery ──────────────────────────────────────────────────────

    async def get_tables(self) -> list[str]:
        assert self._pool, "Not connected"
        rows = await self._pool.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        return [r["table_name"] for r in rows]

    async def get_table_schema(self, table_name: str) -> TableSchema:
        assert self._pool, "Not connected"

        col_rows = await self._pool.fetch(
            """
            SELECT
                c.column_name,
                c.udt_name          AS data_type,
                c.is_nullable,
                c.column_default,
                c.character_maximum_length,
                c.numeric_precision,
                c.numeric_scale,
                COALESCE(pk.is_pk, false) AS is_pk
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT ku.column_name, true AS is_pk
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku
                  ON tc.constraint_name = ku.constraint_name
                 AND tc.table_schema    = ku.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_name = $1
                  AND tc.table_schema = 'public'
            ) pk ON c.column_name = pk.column_name
            WHERE c.table_name   = $1
              AND c.table_schema = 'public'
            ORDER BY c.ordinal_position
            """,
            table_name,
        )

        # Fetch enum types so we can recreate them in the destination
        enum_rows = await self._pool.fetch(
            """
            SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder) AS labels
            FROM pg_type t
            JOIN pg_enum e ON e.enumtypid = t.oid
            JOIN pg_namespace n ON n.oid = t.typnamespace AND n.nspname = 'public'
            GROUP BY t.typname
            """,
        )
        enum_map: dict[str, list[str]] = {r["typname"]: list(r["labels"]) for r in enum_rows}

        columns = [
            ColumnSchema(
                name=r["column_name"],
                data_type=_PG_TYPE_MAP.get(r["data_type"], r["data_type"]),
                is_nullable=r["is_nullable"] == "YES",
                is_primary_key=bool(r["is_pk"]),
                default=r["column_default"],
                max_length=r["character_maximum_length"],
                precision=r["numeric_precision"],
                scale=r["numeric_scale"],
                enum_values=enum_map.get(r["data_type"]),
            )
            for r in col_rows
        ]

        pks = [c.name for c in columns if c.is_primary_key]
        row_count = await self.get_row_count(table_name)

        return TableSchema(
            name=table_name,
            columns=columns,
            primary_keys=pks,
            row_count=row_count,
        )

    async def get_row_count(self, table_name: str) -> int:
        assert self._pool, "Not connected"
        # Use reltuples for large tables as an estimate; fall back to COUNT(*)
        row = await self._pool.fetchrow(
            "SELECT reltuples::BIGINT AS n FROM pg_class WHERE relname = $1",
            table_name,
        )
        if row and row["n"] > 10000:
            return int(row["n"])
        result = await self._pool.fetchval(
            f'SELECT COUNT(*) FROM "{table_name}"'  # noqa: S608
        )
        return int(result or 0)

    # ── Read ──────────────────────────────────────────────────────────────────

    async def fetch_batch(
        self,
        table_name: str,
        offset: int,
        limit: int,
        columns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        assert self._pool, "Not connected"
        cols = ", ".join(f'"{c}"' for c in columns) if columns else "*"
        rows = await self._pool.fetch(
            f'SELECT {cols} FROM "{table_name}" LIMIT $1 OFFSET $2',  # noqa: S608
            limit,
            offset,
        )
        return [dict(r) for r in rows]

    async def stream_table(
        self,
        table_name: str,
        batch_size: int,
        columns: list[str] | None = None,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        assert self._pool, "Not connected"
        offset = 0
        while True:
            batch = await self.fetch_batch(table_name, offset, batch_size, columns)
            if not batch:
                break
            yield batch
            offset += batch_size

    # ── Write ──────────────────────────────────────────────────────────────────

    async def create_table(self, schema: TableSchema) -> None:
        assert self._pool, "Not connected"

        # Create any custom enum types that don't yet exist in the destination
        for col in schema.columns:
            if col.enum_values is not None:
                labels = ", ".join(f"'{v}'" for v in col.enum_values)
                await self._pool.execute(
                    f"DO $$ BEGIN "
                    f"  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{col.data_type}') THEN "
                    f"    CREATE TYPE {col.data_type} AS ENUM ({labels}); "
                    f"  END IF; "
                    f"END $$"
                )

        col_defs = []
        for col in schema.columns:
            dtype = col.data_type
            if col.enum_values is None:
                # Only apply size modifiers for non-enum types
                if col.max_length:
                    dtype = f"{dtype}({col.max_length})"
                elif col.precision and col.scale:
                    dtype = f"{dtype}({col.precision},{col.scale})"
            null_clause = "" if col.is_nullable else " NOT NULL"
            col_defs.append(f'"{col.name}" {dtype}{null_clause}')

        pk_clause = ""
        if schema.primary_keys:
            pks = ", ".join(f'"{k}"' for k in schema.primary_keys)
            pk_clause = f", PRIMARY KEY ({pks})"

        ddl = (
            f'CREATE TABLE IF NOT EXISTS "{schema.name}" '
            f"({', '.join(col_defs)}{pk_clause})"
        )
        await self._pool.execute(ddl)

    async def insert_batch(
        self,
        table_name: str,
        rows: list[dict[str, Any]],
        columns: list[str] | None = None,
    ) -> int:
        if not rows:
            return 0
        assert self._pool, "Not connected"
        cols = columns or list(rows[0].keys())
        quoted_cols = ", ".join(f'"{c}"' for c in cols)
        placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
        sql = f'INSERT INTO "{table_name}" ({quoted_cols}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'  # noqa: S608
        records = [[r.get(c) for c in cols] for r in rows]
        await self._pool.executemany(sql, records)
        return len(rows)

    async def truncate_table(self, table_name: str) -> None:
        assert self._pool, "Not connected"
        await self._pool.execute(f'TRUNCATE TABLE "{table_name}" RESTART IDENTITY CASCADE')

    # ── Misc ──────────────────────────────────────────────────────────────────

    async def execute_query(self, sql: str, params: dict | None = None) -> list[dict[str, Any]]:
        assert self._pool, "Not connected"
        rows = await self._pool.fetch(sql, *(params or {}).values())
        return [dict(r) for r in rows]

    async def table_exists(self, table_name: str) -> bool:
        assert self._pool, "Not connected"
        result = await self._pool.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = $1
            )
            """,
            table_name,
        )
        return bool(result)
