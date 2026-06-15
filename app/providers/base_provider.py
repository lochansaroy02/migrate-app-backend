"""
Abstract base class for all database providers.
Migration logic is written entirely against this interface — no provider-specific
code should leak into migration/, services/, or API layers.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from app.schemas.migration import ColumnSchema, TableSchema


class BaseDatabaseProvider(ABC):
    """Abstract provider — every supported database must implement this."""

    # ── Lifecycle ────────────────────────────────────────────────────────────

    @abstractmethod
    async def connect(self) -> None:
        """Open the connection / connection pool."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection / connection pool gracefully."""

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str, float]:
        """
        Verify connectivity.
        Returns (success, message, latency_ms).
        Must not raise; all exceptions must be caught internally.
        """

    # ── Schema discovery ─────────────────────────────────────────────────────

    @abstractmethod
    async def get_tables(self) -> list[str]:
        """Return a list of table names in the target database/schema."""

    @abstractmethod
    async def get_table_schema(self, table_name: str) -> TableSchema:
        """Return column definitions, primary keys, and estimated row count."""

    @abstractmethod
    async def get_row_count(self, table_name: str) -> int:
        """Return the exact (or estimated) number of rows in *table_name*."""

    # ── Read ──────────────────────────────────────────────────────────────────

    @abstractmethod
    async def fetch_batch(
        self,
        table_name: str,
        offset: int,
        limit: int,
        columns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch a batch of rows from *table_name*.
        Returns a list of dicts keyed by column name.
        Must never load the entire table into memory.
        """

    @abstractmethod
    def stream_table(
        self,
        table_name: str,
        batch_size: int,
        columns: list[str] | None = None,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """
        Async-generator that yields batches of rows until the table is exhausted.
        Preferred over fetch_batch for large tables.
        """

    # ── Write ─────────────────────────────────────────────────────────────────

    @abstractmethod
    async def create_table(self, schema: TableSchema) -> None:
        """
        Create *schema.name* in the destination database.
        Must be idempotent (CREATE TABLE IF NOT EXISTS or equivalent).
        """

    @abstractmethod
    async def insert_batch(
        self,
        table_name: str,
        rows: list[dict[str, Any]],
        columns: list[str] | None = None,
    ) -> int:
        """
        Insert *rows* into *table_name*.
        Returns the number of rows actually inserted.
        """

    @abstractmethod
    async def truncate_table(self, table_name: str) -> None:
        """Remove all rows from *table_name* without dropping the table."""

    # ── Misc ──────────────────────────────────────────────────────────────────

    @abstractmethod
    async def execute_query(self, sql: str, params: dict | None = None) -> list[dict[str, Any]]:
        """Execute an arbitrary read-only query and return the result rows."""

    @abstractmethod
    async def table_exists(self, table_name: str) -> bool:
        """Return True if *table_name* already exists in the destination."""

    # ── Helpers (default implementations) ────────────────────────────────────

    async def __aenter__(self) -> "BaseDatabaseProvider":
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.disconnect()
