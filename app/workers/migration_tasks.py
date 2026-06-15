"""
Celery task that executes a full migration in a background worker.
Uses asyncio.run() so the async provider/executor code runs cleanly.
Progress is persisted to the application DB and broadcast via WebSocket.
"""

import asyncio
import json
from datetime import datetime, timezone

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select

from app.core.constants import MigrationStatus
from app.core.database import AsyncSessionLocal
from app.migration.executor import MigrationExecutor
from app.migration.planner import MigrationPlanner
from app.models.migration import Migration
from app.models.migration_log import MigrationLog
from app.providers import get_provider
from app.schemas.migration import MigrationPlan, MigrationSettings
from app.utils.encryption import decrypt_credentials
from app.utils.helpers import Timer, new_uuid
from app.utils.logger import get_logger
from app.websockets.manager import ws_manager
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


class MigrationTask(Task):
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        migration_id = args[0] if args else None
        if migration_id:
            asyncio.run(_mark_failed(migration_id, str(exc)))


async def _mark_failed(migration_id: str, error: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Migration).where(Migration.id == migration_id))
        record = result.scalar_one_or_none()
        if record:
            record.status = MigrationStatus.FAILED
            record.error_message = error[:2000]
            record.completed_at = datetime.now(timezone.utc)
            await db.commit()
    await ws_manager.send_failed(migration_id, error)


@celery_app.task(bind=True, base=MigrationTask, name="migration.run")
def run_migration_task(self: Task, migration_id: str) -> dict:
    return asyncio.run(_execute(migration_id))


async def _execute(migration_id: str) -> dict:
    timer = Timer()
    logger.info("Migration task started", migration_id=migration_id)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Migration).where(Migration.id == migration_id))
        record = result.scalar_one_or_none()
        if not record:
            raise ValueError(f"Migration {migration_id} not found in DB")

        # Load config
        tables: list[str] = json.loads(record.tables_config or "[]")
        settings_dict: dict = json.loads(record.settings or "{}")
        mig_settings = MigrationSettings(**settings_dict)

        src_creds = decrypt_credentials(record.source_connection)
        dst_creds = decrypt_credentials(record.destination_connection)

        # Mark running
        record.status = MigrationStatus.RUNNING
        record.started_at = datetime.now(timezone.utc)
        await db.commit()

    src_type = src_creds.get("database_type")
    dst_type = dst_creds.get("database_type")
    if not src_type or not dst_type:
        raise ValueError("database_type missing from stored credentials — cannot start migration.")

    src_provider = get_provider(src_type, src_creds)
    dst_provider = get_provider(dst_type, dst_creds)

    try:
        async with src_provider, dst_provider:
            # Re-build plan inside the worker so connections are fresh
            planner = MigrationPlanner(src_provider, dst_provider, tables)
            plan: MigrationPlan = await planner.build_plan()

            # ── Callbacks ────────────────────────────────────────────────────

            async def on_progress(
                table_name: str,
                rows_in_table: int,
                total_processed: int,
                error: str | None,
            ) -> None:
                from app.utils.helpers import calculate_progress, calculate_speed, estimate_time_remaining
                elapsed = timer.elapsed()
                async with AsyncSessionLocal() as db2:
                    r = (await db2.execute(select(Migration).where(Migration.id == migration_id))).scalar_one()
                    r.processed_rows = total_processed
                    r.current_table = table_name
                    await db2.commit()

                progress = calculate_progress(total_processed, plan.total_rows)
                speed = calculate_speed(total_processed, elapsed)
                eta = estimate_time_remaining(total_processed, plan.total_rows, elapsed)

                await ws_manager.send_progress(
                    migration_id,
                    status=MigrationStatus.RUNNING,
                    progress=progress,
                    current_table=table_name,
                    processed_rows=total_processed,
                    total_rows=plan.total_rows,
                    speed=speed,
                    estimated_time_remaining=eta,
                )

            async def on_log(level: str, message: str, table_name: str | None) -> None:
                log_entry = MigrationLog(
                    id=new_uuid(),
                    migration_id=migration_id,
                    level=level,
                    message=message,
                    table_name=table_name,
                )
                async with AsyncSessionLocal() as db3:
                    db3.add(log_entry)
                    await db3.commit()
                await ws_manager.send_log(migration_id, level, message, table_name)

            executor = MigrationExecutor(
                source=src_provider,
                destination=dst_provider,
                plan=plan,
                batch_size=mig_settings.batch_size,
                include_schema=mig_settings.include_schema,
                include_data=mig_settings.include_data,
                truncate_destination=mig_settings.truncate_destination,
                max_retries=mig_settings.max_retries,
                continue_on_error=mig_settings.continue_on_error,
                on_progress=on_progress,
                on_log=on_log,
            )
            exec_result = await executor.run()

    except SoftTimeLimitExceeded:
        await _mark_failed(migration_id, "Task exceeded time limit and was terminated.")
        raise
    except Exception as exc:
        await _mark_failed(migration_id, str(exc))
        raise

    # ── Finalise ──────────────────────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        r = (await db.execute(select(Migration).where(Migration.id == migration_id))).scalar_one()
        failed_tables = exec_result.get("failed_tables", [])
        r.status = MigrationStatus.FAILED if failed_tables else MigrationStatus.COMPLETED
        r.completed_tables = len(exec_result.get("completed_tables", []))
        r.processed_rows = exec_result.get("total_rows_migrated", 0)
        r.completed_at = datetime.now(timezone.utc)
        r.current_table = None
        if failed_tables:
            r.error_message = f"Tables failed: {', '.join(failed_tables)}"
        await db.commit()

    await ws_manager.send_completed(migration_id, exec_result)
    logger.info("Migration task completed", migration_id=migration_id, elapsed=timer.elapsed())
    return exec_result
