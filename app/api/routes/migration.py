from fastapi import APIRouter, Depends, Query, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.migration import (
    MigrationCreateRequest,
    MigrationCreateResponse,
    MigrationLogsResponse,
    MigrationStatusResponse,
)
from app.services.migration_service import migration_service
from app.services.websocket_service import websocket_service

router = APIRouter(prefix="/migration", tags=["migration"])


@router.post(
    "/create",
    response_model=MigrationCreateResponse,
    status_code=201,
    summary="Create a migration and generate a plan",
)
async def create_migration(
    req: MigrationCreateRequest,
    db: AsyncSession = Depends(get_session),
) -> MigrationCreateResponse:
    """
    Validates both connections, reads source schema, generates a migration plan,
    and persists the migration record.  Returns a migration_id to use for subsequent calls.
    """
    return await migration_service.create_migration(req, db)


@router.post(
    "/start/{migration_id}",
    summary="Start executing a migration in the background",
)
async def start_migration(
    migration_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """
    Enqueues the migration as a Celery task.
    The migration must be in 'pending' or 'failed' status.
    """
    return await migration_service.start_migration(migration_id, db)


@router.get(
    "/{migration_id}",
    response_model=MigrationStatusResponse,
    summary="Get migration status and progress",
)
async def get_migration_status(
    migration_id: str,
    db: AsyncSession = Depends(get_session),
) -> MigrationStatusResponse:
    return await migration_service.get_status(migration_id, db)


@router.get(
    "/{migration_id}/logs",
    response_model=MigrationLogsResponse,
    summary="Get migration logs",
)
async def get_migration_logs(
    migration_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_session),
) -> MigrationLogsResponse:
    return await migration_service.get_logs(migration_id, db, limit=limit, offset=offset)


@router.post(
    "/{migration_id}/cancel",
    summary="Cancel a running migration",
)
async def cancel_migration(
    migration_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict:
    return await migration_service.cancel_migration(migration_id, db)


# ── WebSocket ─────────────────────────────────────────────────────────────────

@router.websocket("/{migration_id}/ws")
async def migration_websocket(migration_id: str, ws: WebSocket) -> None:
    """
    Real-time WebSocket feed for a migration.
    Sends progress, log, completed, and failed events as JSON.
    """
    await websocket_service.handle_migration_ws(migration_id, ws)
