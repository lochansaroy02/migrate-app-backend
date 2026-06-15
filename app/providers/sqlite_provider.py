"""
SQLite provider using aiosqlite.
Primarily useful for development, testing, and small embedded datasets.
"""

import time
from collections.abc import AsyncIterator
from typing import Any

import aiosqlite

from app.providers.base_provider import BaseDatabaseProvider
from app.schemas.migration import ColumnSchema, TableSchema
from app.utils.logger import get_logger

logger = get_logger(__name__)

_SQLITE_AFFINITY_MAP: dict[str, str] = {
    "integer": "INTEGER",
    "int": "INTEGER",
    "tinyint": "SMALLINT",
    "smallint": "SMALLINT",
    "mediumint": "INTEGER",
    "bigint": "BIGINT",
    "real": "FLOAT",
    "float": "FLOAT",
    "double": "DOUBLE",
    "numeric": "DECIMAL",
    "decimal": "DECIMAL",
    "text": "TEXT",
    "varchar": "VARCHAR",
    "character": "VARCHAR",
    "char": "CHAR",
    "clob": "TEXT",
    "blob": "BLOB",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "datetime": "DATETIME",
    "timestamp": "TIMESTAMP",
    "json": "JSON",
}


def _resolve_path(credentials: dict) -> str:
    if "database_url" in credentials and credentials["database_url"]:
        url = credentials["database_url"]
        return url.replace("sqlite:///", "").replace("sqlite://", "")
    return credentials.get("file_path", ":memory:")


class SQLiteProvider(BaseDatabaseProvider):
    def __init__(self, credentials: dict) -> None:
        self._path = _resolve_path(credentials)
        self._conn: aiosqlite.Connection | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")

    async def disconnect(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def test_connection(self) -> tuple[bool, str, float]:
        start = time.monotonic()
        try:
            conn = await aiosqlite.connect(self._path, timeout=5)
            await conn.execute("SELECT 1")
            await conn.close()
            latency = (time.monotonic() - start) * 1000
            return True, "Connection successful", round(latency, 2)
        except Exception as exc:
            return False, str(exc), 0.0

    # ── Schema discovery ──────────────────────────────────────────────────────

    async def get_tables(self) -> list[str]:
        assert self._conn, "Not connected"
        async with self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ) as cur:
            rows = await cur.fetchall()
        return [r[0] for r in rows]

    async def get_table_schema(self, table_name: str) -> TableSchema:
        assert self._conn, "Not connected"

        async with self._conn.execute(f"PRAGMA table_info('{table_name}')") as cur:  # noqa: S608
            info_rows = await cur.fetchall()

        columns = []
        pks = []
        for row in info_rows:
            # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
            col_type = str(row[2]).lower().split("(")[0].strip()
            mapped = _SQLITE_AFFINITY_MAP.get(col_type, row[2].upper() if row[2] else "TEXT")
            is_pk = bool(row[5])
            col = ColumnSchema(
                name=row[1],
                data_type=mapped,
                is_nullable=not bool(row[3]),
                is_primary_key=is_pk,
                default=str(row[4]) if row[4] is not None else None,
            )
            columns.append(col)
            if is_pk:
                pks.append(row[1])

        row_count = await self.get_row_count(table_name)
        return TableSchema(name=table_name, columns=columns, primary_keys=pks, row_count=row_count)

    async def get_row_count(self, table_name: str) -> int:
        assert self._conn, "Not connected"
        async with self._conn.execute(
            f"SELECT COUNT(*) FROM \"{table_name}\""  # noqa: S608
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    # ── Read ──────────────────────────────────────────────────────────────────

    async def fetch_batch(
        self,
        table_name: str,
        offset: int,
        limit: int,
        columns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        assert self._conn, "Not connected"
        cols = ", ".join(f'"{c}"' for c in columns) if columns else "*"
        async with self._conn.execute(
            f'SELECT {cols} FROM "{table_name}" LIMIT ? OFFSET ?',  # noqa: S608
            (limit, offset),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def stream_table(
        self,
        table_name: str,
        batch_size: int,
        columns: list[str] | None = None,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        offset = 0
        while True:
            batch = await self.fetch_batch(table_name, offset, batch_size, columns)
            if not batch:
                break
            yield batch
            offset += batch_size

    # ── Write ──────────────────────────────────────────────────────────────────

    async def create_table(self, schema: TableSchema) -> None:
        assert self._conn, "Not connected"
        col_defs = []
        for col in schema.columns:
            dtype = col.data_type
            null_clause = "" if col.is_nullable else " NOT NULL"
            pk_clause = " PRIMARY KEY" if col.is_primary_key and len(schema.primary_keys) == 1 else ""
            col_defs.append(f'"{col.name}" {dtype}{null_clause}{pk_clause}')

        # Composite primary key
        pk_clause = ""
        if len(schema.primary_keys) > 1:
            pks = ", ".join(f'"{k}"' for k in schema.primary_keys)
            pk_clause = f", PRIMARY KEY ({pks})"

        ddl = (
            f'CREATE TABLE IF NOT EXISTS "{schema.name}" '
            f"({', '.join(col_defs)}{pk_clause})"
        )
        await self._conn.execute(ddl)
        await self._conn.commit()

    async def insert_batch(
        self,
        table_name: str,
        rows: list[dict[str, Any]],
        columns: list[str] | None = None,
    ) -> int:
        if not rows:
            return 0
        assert self._conn, "Not connected"
        cols = columns or list(rows[0].keys())
        quoted_cols = ", ".join(f'"{c}"' for c in cols)
        placeholders = ", ".join(["?"] * len(cols))
        sql = f'INSERT OR IGNORE INTO "{table_name}" ({quoted_cols}) VALUES ({placeholders})'  # noqa: S608
        records = [tuple(r.get(c) for c in cols) for r in rows]
        await self._conn.executemany(sql, records)
        await self._conn.commit()
        return len(rows)

    async def truncate_table(self, table_name: str) -> None:
        assert self._conn, "Not connected"
        await self._conn.execute(f'DELETE FROM "{table_name}"')
        await self._conn.commit()

    async def execute_query(self, sql: str, params: dict | None = None) -> list[dict[str, Any]]:
        assert self._conn, "Not connected"
        async with self._conn.execute(sql, list((params or {}).values())) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def table_exists(self, table_name: str) -> bool:
        assert self._conn, "Not connected"
        async with self._conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ) as cur:
            row = await cur.fetchone()
        return bool(row and row[0] > 0)
