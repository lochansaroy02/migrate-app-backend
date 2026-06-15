"""
MySQL / MariaDB provider using aiomysql for async I/O.
"""

import time
from collections.abc import AsyncIterator
from typing import Any

import aiomysql

from app.providers.base_provider import BaseDatabaseProvider
from app.schemas.migration import ColumnSchema, TableSchema
from app.utils.logger import get_logger

logger = get_logger(__name__)

_MYSQL_TYPE_MAP: dict[str, str] = {
    "tinyint": "TINYINT",
    "smallint": "SMALLINT",
    "mediumint": "MEDIUMINT",
    "int": "INT",
    "bigint": "BIGINT",
    "float": "FLOAT",
    "double": "DOUBLE",
    "decimal": "DECIMAL",
    "numeric": "DECIMAL",
    "char": "CHAR",
    "varchar": "VARCHAR",
    "tinytext": "TINYTEXT",
    "text": "TEXT",
    "mediumtext": "MEDIUMTEXT",
    "longtext": "LONGTEXT",
    "tinyblob": "TINYBLOB",
    "blob": "BLOB",
    "mediumblob": "MEDIUMBLOB",
    "longblob": "LONGBLOB",
    "date": "DATE",
    "time": "TIME",
    "datetime": "DATETIME",
    "timestamp": "TIMESTAMP",
    "year": "YEAR",
    "bool": "BOOLEAN",
    "boolean": "BOOLEAN",
    "bit": "BIT",
    "json": "JSON",
    "enum": "VARCHAR",
    "set": "VARCHAR",
}


def _parse_credentials(creds: dict) -> dict:
    if "database_url" in creds and creds["database_url"]:
        import urllib.parse as up
        r = up.urlparse(creds["database_url"])
        return {
            "host": r.hostname or "localhost",
            "port": r.port or 3306,
            "user": r.username or "",
            "password": r.password or "",
            "db": r.path.lstrip("/"),
        }
    return {
        "host": creds.get("host", "localhost"),
        "port": int(creds.get("port", 3306)),
        "user": creds.get("username", ""),
        "password": creds.get("password", ""),
        "db": creds.get("database", ""),
    }


class MySQLProvider(BaseDatabaseProvider):
    def __init__(self, credentials: dict) -> None:
        self._params = _parse_credentials(credentials)
        self._pool: aiomysql.Pool | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        self._pool = await aiomysql.create_pool(
            **self._params,
            cursorclass=aiomysql.DictCursor,
            autocommit=True,
            minsize=1,
            maxsize=5,
            connect_timeout=10,
        )

    async def disconnect(self) -> None:
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None

    async def test_connection(self) -> tuple[bool, str, float]:
        start = time.monotonic()
        try:
            conn = await aiomysql.connect(**self._params, connect_timeout=10)
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
            conn.close()
            latency = (time.monotonic() - start) * 1000
            return True, "Connection successful", round(latency, 2)
        except Exception as exc:
            return False, str(exc), 0.0

    # ── Schema discovery ──────────────────────────────────────────────────────

    async def get_tables(self) -> list[str]:
        assert self._pool, "Not connected"
        db_name = self._params["db"]
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT TABLE_NAME FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
                    ORDER BY TABLE_NAME
                    """,
                    (db_name,),
                )
                rows = await cur.fetchall()
        return [r["TABLE_NAME"] for r in rows]

    async def get_table_schema(self, table_name: str) -> TableSchema:
        assert self._pool, "Not connected"
        db_name = self._params["db"]
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT
                        COLUMN_NAME, DATA_TYPE, IS_NULLABLE,
                        COLUMN_DEFAULT, CHARACTER_MAXIMUM_LENGTH,
                        NUMERIC_PRECISION, NUMERIC_SCALE,
                        COLUMN_KEY
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                    ORDER BY ORDINAL_POSITION
                    """,
                    (db_name, table_name),
                )
                col_rows = await cur.fetchall()

        columns = [
            ColumnSchema(
                name=r["COLUMN_NAME"],
                data_type=_MYSQL_TYPE_MAP.get(r["DATA_TYPE"].lower(), r["DATA_TYPE"].upper()),
                is_nullable=r["IS_NULLABLE"] == "YES",
                is_primary_key=r["COLUMN_KEY"] == "PRI",
                default=r["COLUMN_DEFAULT"],
                max_length=r["CHARACTER_MAXIMUM_LENGTH"],
                precision=r["NUMERIC_PRECISION"],
                scale=r["NUMERIC_SCALE"],
            )
            for r in col_rows
        ]
        pks = [c.name for c in columns if c.is_primary_key]
        row_count = await self.get_row_count(table_name)
        return TableSchema(name=table_name, columns=columns, primary_keys=pks, row_count=row_count)

    async def get_row_count(self, table_name: str) -> int:
        assert self._pool, "Not connected"
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"SELECT COUNT(*) AS n FROM `{table_name}`")  # noqa: S608
                row = await cur.fetchone()
        return int(row["n"] if row else 0)

    # ── Read ──────────────────────────────────────────────────────────────────

    async def fetch_batch(
        self,
        table_name: str,
        offset: int,
        limit: int,
        columns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        assert self._pool, "Not connected"
        cols = ", ".join(f"`{c}`" for c in columns) if columns else "*"
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT {cols} FROM `{table_name}` LIMIT %s OFFSET %s",  # noqa: S608
                    (limit, offset),
                )
                return list(await cur.fetchall())

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
        assert self._pool, "Not connected"
        col_defs = []
        for col in schema.columns:
            dtype = col.data_type
            if col.max_length:
                dtype = f"{dtype}({col.max_length})"
            elif col.precision and col.scale:
                dtype = f"{dtype}({col.precision},{col.scale})"
            null_clause = "" if col.is_nullable else " NOT NULL"
            col_defs.append(f"`{col.name}` {dtype}{null_clause}")

        pk_clause = ""
        if schema.primary_keys:
            pks = ", ".join(f"`{k}`" for k in schema.primary_keys)
            pk_clause = f", PRIMARY KEY ({pks})"

        ddl = (
            f"CREATE TABLE IF NOT EXISTS `{schema.name}` "
            f"({', '.join(col_defs)}{pk_clause}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        )
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(ddl)

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
        quoted_cols = ", ".join(f"`{c}`" for c in cols)
        placeholders = ", ".join(["%s"] * len(cols))
        sql = (
            f"INSERT IGNORE INTO `{table_name}` ({quoted_cols}) VALUES ({placeholders})"  # noqa: S608
        )
        records = [tuple(r.get(c) for c in cols) for r in rows]
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(sql, records)
        return len(rows)

    async def truncate_table(self, table_name: str) -> None:
        assert self._pool, "Not connected"
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"TRUNCATE TABLE `{table_name}`")

    async def execute_query(self, sql: str, params: dict | None = None) -> list[dict[str, Any]]:
        assert self._pool, "Not connected"
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, list((params or {}).values()))
                return list(await cur.fetchall())

    async def table_exists(self, table_name: str) -> bool:
        assert self._pool, "Not connected"
        db_name = self._params["db"]
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT COUNT(*) AS n FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                    """,
                    (db_name, table_name),
                )
                row = await cur.fetchone()
        return bool(row and row["n"] > 0)
