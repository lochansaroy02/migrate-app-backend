"""
Executes a MigrationPlan table-by-table, batch-by-batch.
All progress updates go through the ProgressCallback so the caller
(Celery task) can persist state without executor knowing about the DB.
"""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from app.migration.mapper import apply_mappings
from app.providers.base_provider import BaseDatabaseProvider
from app.schemas.migration import MigrationPlan, MigrationTablePlan
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Type alias for progress callback
# (table_name, rows_done_in_table, rows_done_total, error_msg | None) -> Coroutine
ProgressCallback = Callable[[str, int, int, str | None], Coroutine[Any, Any, None]]


class MigrationExecutor:
    def __init__(
        self,
        source: BaseDatabaseProvider,
        destination: BaseDatabaseProvider,
        plan: MigrationPlan,
        batch_size: int = 1000,
        include_schema: bool = True,
        include_data: bool = True,
        truncate_destination: bool = False,
        max_retries: int = 3,
        continue_on_error: bool = False,
        on_progress: ProgressCallback | None = None,
        on_log: Callable[[str, str, str | None], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self._source = source
        self._destination = destination
        self._plan = plan
        self._batch_size = batch_size
        self._include_schema = include_schema
        self._include_data = include_data
        self._truncate = truncate_destination
        self._max_retries = max_retries
        self._continue_on_error = continue_on_error
        self._on_progress = on_progress
        self._on_log = on_log
        self._total_rows_processed = 0

    # ── Public entry point ────────────────────────────────────────────────────

    async def run(self) -> dict:
        results = {
            "completed_tables": [],
            "skipped_tables": [],
            "failed_tables": [],
            "total_rows_migrated": 0,
        }

        for table_plan in self._plan.tables:
            if table_plan.status == "skipped":
                results["skipped_tables"].append(table_plan.table_name)
                await self._log("WARNING", f"Skipping table '{table_plan.table_name}' (incompatible schema)")
                continue

            success = await self._migrate_table(table_plan)
            if success:
                results["completed_tables"].append(table_plan.table_name)
            else:
                results["failed_tables"].append(table_plan.table_name)
                if not self._continue_on_error:
                    break

        results["total_rows_migrated"] = self._total_rows_processed
        return results

    # ── Per-table logic ───────────────────────────────────────────────────────

    async def _migrate_table(self, table_plan: MigrationTablePlan) -> bool:
        table = table_plan.table_name
        await self._log("INFO", f"Starting migration of table '{table}'", table)

        # 1. Create table in destination if needed
        if self._include_schema:
            try:
                await self._destination.create_table(table_plan.source_schema)
                await self._log("INFO", f"Table '{table}' ensured in destination", table)
            except Exception as exc:
                await self._log("ERROR", f"Failed to create table '{table}': {exc}", table)
                return False

        # 2. Optionally truncate existing rows
        if self._truncate:
            try:
                await self._destination.truncate_table(table)
                await self._log("INFO", f"Truncated destination table '{table}'", table)
            except Exception as exc:
                await self._log("WARNING", f"Could not truncate '{table}': {exc}", table)

        # 3. Stream data in batches
        if not self._include_data:
            await self._log("INFO", f"Skipping data copy for '{table}' (include_data=false)", table)
            return True

        active_mappings = [m for m in table_plan.column_mappings if m["include"]]
        columns = [m["source_col"] for m in active_mappings] if active_mappings else None

        offset = 0
        rows_for_table = 0
        retry_count = 0

        while True:
            try:
                batch = await self._source.fetch_batch(table, offset, self._batch_size, columns)
            except Exception as exc:
                await self._log("ERROR", f"Failed to fetch batch at offset {offset} for '{table}': {exc}", table)
                if retry_count < self._max_retries:
                    retry_count += 1
                    await asyncio.sleep(2 ** retry_count)
                    continue
                return False

            if not batch:
                break

            # Apply column mappings / type coercions
            if active_mappings:
                transformed = apply_mappings(batch, table_plan.column_mappings)
            else:
                transformed = batch

            # Insert with retry
            insert_ok = await self._insert_with_retry(table, transformed)
            if not insert_ok:
                return False

            count = len(batch)
            rows_for_table += count
            self._total_rows_processed += count
            offset += count
            retry_count = 0

            if self._on_progress:
                await self._on_progress(table, rows_for_table, self._total_rows_processed, None)

        await self._log("INFO", f"Completed '{table}': {rows_for_table} rows migrated", table)
        return True

    async def _insert_with_retry(self, table: str, rows: list[dict]) -> bool:
        for attempt in range(self._max_retries + 1):
            try:
                await self._destination.insert_batch(table, rows)
                return True
            except Exception as exc:
                await self._log(
                    "WARNING",
                    f"Insert attempt {attempt + 1}/{self._max_retries + 1} failed for '{table}': {exc}",
                    table,
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(2 ** attempt)
        await self._log("ERROR", f"All insert retries exhausted for table '{table}'", table)
        return False

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _log(self, level: str, message: str, table: str | None = None) -> None:
        bound = logger.bind(table=table)
        lvl = level.upper()
        if lvl == "DEBUG":
            bound.debug(message)
        elif lvl == "WARNING":
            bound.warning(message)
        elif lvl == "ERROR":
            bound.error(message)
        elif lvl == "CRITICAL":
            bound.critical(message)
        else:
            bound.info(message)
        if self._on_log:
            await self._on_log(level, message, table)
