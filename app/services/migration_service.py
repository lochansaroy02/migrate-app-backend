"""
Migration service — CRUD for migration records and plan generation.
The actual execution is delegated to Celery workers.
"""

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MigrationStatus
from app.migration.planner import MigrationPlanner
from app.models.migration import Migration
from app.models.migration_log import MigrationLog
from app.providers import get_provider
from app.schemas.migration import (
    MigrationCreateRequest,
    MigrationCreateResponse,
    MigrationLogEntry,
    MigrationLogsResponse,
    MigrationPlan,
    MigrationStatusResponse,
)
from app.utils.encryption import decrypt_credentials, encrypt_credentials
from app.utils.helpers import (
    calculate_progress,
    calculate_speed,
    estimate_time_remaining,
    new_uuid,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _creds_to_dict(conn_schema) -> dict:
    return {k: v for k, v in conn_schema.model_dump().items() if v is not None}


class MigrationService:
    # ── Create ────────────────────────────────────────────────────────────────

    async def create_migration(
        self,
        req: MigrationCreateRequest,
        db: AsyncSession,
    ) -> MigrationCreateResponse:
        src_creds = _creds_to_dict(req.source)
        dst_creds = _creds_to_dict(req.destination)

        # Validate both connections are reachable before saving anything
        src_provider = get_provider(req.source.database_type.value, src_creds)
        dst_provider = get_provider(req.destination.database_type.value, dst_creds)

        src_ok, src_msg, _ = await src_provider.test_connection()
        if not src_ok:
            raise ValueError(f"Source connection failed: {src_msg}")

        dst_ok, dst_msg, _ = await dst_provider.test_connection()
        if not dst_ok:
            raise ValueError(f"Destination connection failed: {dst_msg}")

        # Build plan (schema read) while connections are proven good
        async with src_provider, dst_provider:
            planner = MigrationPlanner(src_provider, dst_provider, req.tables)
            plan: MigrationPlan = await planner.build_plan()

        migration_id = new_uuid()
        record = Migration(
            id=migration_id,
            status=MigrationStatus.PENDING,
            source_connection=encrypt_credentials(src_creds),
            destination_connection=encrypt_credentials(dst_creds),
            tables_config=json.dumps(req.tables),
            migration_plan=plan.model_dump_json(),
            settings=req.settings.model_dump_json(),
            total_tables=len(req.tables),
            total_rows=plan.total_rows,
        )
        db.add(record)
        await db.commit()

        logger.info("Migration created", migration_id=migration_id, total_rows=plan.total_rows)
        return MigrationCreateResponse(migration_id=migration_id)

    # ── Status ────────────────────────────────────────────────────────────────

    async def get_status(
        self,
        migration_id: str,
        db: AsyncSession,
    ) -> MigrationStatusResponse:
        record = await self._get_or_404(migration_id, db)

        elapsed = 0.0
        if record.started_at:
            end = record.completed_at or datetime.now(timezone.utc)
            elapsed = (end - record.started_at).total_seconds()

        progress = calculate_progress(record.processed_rows, record.total_rows)
        speed = calculate_speed(record.processed_rows, elapsed)
        eta = estimate_time_remaining(record.processed_rows, record.total_rows, elapsed)

        return MigrationStatusResponse(
            id=record.id,
            status=MigrationStatus(record.status),
            progress=progress,
            current_table=record.current_table,
            processed_rows=record.processed_rows,
            total_rows=record.total_rows,
            speed=speed,
            estimated_time_remaining=eta,
            started_at=record.started_at,
            completed_at=record.completed_at,
            error_message=record.error_message,
        )

    # ── Logs ──────────────────────────────────────────────────────────────────

    async def get_logs(
        self,
        migration_id: str,
        db: AsyncSession,
        limit: int = 200,
        offset: int = 0,
    ) -> MigrationLogsResponse:
        await self._get_or_404(migration_id, db)

        stmt = (
            select(MigrationLog)
            .where(MigrationLog.migration_id == migration_id)
            .order_by(MigrationLog.created_at)
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        log_rows = result.scalars().all()

        from sqlalchemy import func
        count_result = await db.execute(
            select(func.count()).where(MigrationLog.migration_id == migration_id)
        )
        total = count_result.scalar_one()

        entries = [
            MigrationLogEntry(
                id=row.id,
                timestamp=row.created_at,
                level=row.level,
                message=row.message,
                table_name=row.table_name,
            )
            for row in log_rows
        ]
        return MigrationLogsResponse(migration_id=migration_id, logs=entries, total=total)

    # ── Start (dispatches Celery task) ────────────────────────────────────────

    async def start_migration(self, migration_id: str, db: AsyncSession) -> dict:
        record = await self._get_or_404(migration_id, db)
        if record.status not in (MigrationStatus.PENDING, MigrationStatus.FAILED):
            raise ValueError(
                f"Migration is in '{record.status}' state and cannot be started."
            )

        # Import here to avoid circular imports at module load time
        from app.workers.migration_tasks import run_migration_task

        task = run_migration_task.delay(migration_id)
        record.celery_task_id = task.id
        record.status = MigrationStatus.RUNNING
        record.started_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info("Migration started", migration_id=migration_id, task_id=task.id)
        return {"migration_id": migration_id, "task_id": task.id}

    # ── Cancel ────────────────────────────────────────────────────────────────

    async def cancel_migration(self, migration_id: str, db: AsyncSession) -> dict:
        from app.workers.celery_app import celery_app

        record = await self._get_or_404(migration_id, db)
        if record.status != MigrationStatus.RUNNING:
            raise ValueError("Only running migrations can be cancelled.")

        if record.celery_task_id:
            celery_app.control.revoke(record.celery_task_id, terminate=True, signal="SIGTERM")

        record.status = MigrationStatus.CANCELLED
        record.completed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"migration_id": migration_id, "status": "cancelled"}

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _get_or_404(self, migration_id: str, db: AsyncSession) -> Migration:
        result = await db.execute(
            select(Migration).where(Migration.id == migration_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=f"Migration '{migration_id}' not found.")
        return record


migration_service = MigrationService()
