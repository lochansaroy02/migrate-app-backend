"""
In-process WebSocket connection manager.
Clients subscribe to a migration_id channel and receive real-time progress events.
Designed to work with a single FastAPI process; for multi-worker deployments,
replace the in-memory dict with a Redis pub/sub backend.
"""

import asyncio
import json
from collections import defaultdict
from typing import Any

from fastapi import WebSocket
from fastapi.websockets import WebSocketState

from app.utils.logger import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        # migration_id -> set of active WebSocket connections
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, migration_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[migration_id].add(ws)
        logger.info("WebSocket connected", migration_id=migration_id)

    async def disconnect(self, migration_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._connections[migration_id].discard(ws)
            if not self._connections[migration_id]:
                del self._connections[migration_id]
        logger.info("WebSocket disconnected", migration_id=migration_id)

    async def broadcast(self, migration_id: str, payload: dict[str, Any]) -> None:
        """Send *payload* to all subscribers of *migration_id*."""
        message = json.dumps(payload, default=str)
        stale: list[WebSocket] = []

        async with self._lock:
            sockets = set(self._connections.get(migration_id, set()))

        for ws in sockets:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(message)
            except Exception:
                stale.append(ws)

        if stale:
            async with self._lock:
                for ws in stale:
                    self._connections[migration_id].discard(ws)

    async def send_progress(
        self,
        migration_id: str,
        status: str,
        progress: int,
        current_table: str | None,
        processed_rows: int,
        total_rows: int,
        speed: int = 0,
        estimated_time_remaining: int = 0,
    ) -> None:
        await self.broadcast(
            migration_id,
            {
                "type": "progress",
                "migration_id": migration_id,
                "status": status,
                "progress": progress,
                "current_table": current_table,
                "processed_rows": processed_rows,
                "total_rows": total_rows,
                "speed": speed,
                "estimated_time_remaining": estimated_time_remaining,
            },
        )

    async def send_log(
        self,
        migration_id: str,
        level: str,
        message: str,
        table_name: str | None = None,
    ) -> None:
        await self.broadcast(
            migration_id,
            {
                "type": "log",
                "migration_id": migration_id,
                "level": level,
                "message": message,
                "table_name": table_name,
            },
        )

    async def send_completed(self, migration_id: str, result: dict) -> None:
        await self.broadcast(
            migration_id,
            {"type": "completed", "migration_id": migration_id, **result},
        )

    async def send_failed(self, migration_id: str, error: str) -> None:
        await self.broadcast(
            migration_id,
            {"type": "failed", "migration_id": migration_id, "error": error},
        )


ws_manager = ConnectionManager()
