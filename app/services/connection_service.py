"""
Connection service — validates credentials and tests connectivity.
"""

import time
from typing import Any

from app.core.constants import ConnectionMethod, DatabaseType
from app.providers import get_provider
from app.schemas.connection import ConnectionTestRequest, ConnectionTestResponse
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _build_credentials(req: ConnectionTestRequest) -> dict[str, Any]:
    """Extract raw credential dict from the request model."""
    if req.connection_method == ConnectionMethod.URL:
        return {
            "database_url": req.database_url,
            "connection_method": req.connection_method.value,
        }
    creds: dict[str, Any] = {
        "connection_method": req.connection_method.value,
        "host": req.host,
        "port": req.port,
        "database": req.database,
        "username": req.username,
        "password": req.password,
    }
    if req.database_type == DatabaseType.SQLITE:
        creds["file_path"] = req.file_path
    return creds


class ConnectionService:
    async def test_connection(self, req: ConnectionTestRequest) -> ConnectionTestResponse:
        credentials = _build_credentials(req)
        try:
            provider = get_provider(req.database_type.value, credentials)
        except NotImplementedError as exc:
            return ConnectionTestResponse(success=False, message=str(exc))

        success, message, latency_ms = await provider.test_connection()
        logger.info(
            "Connection test",
            db_type=req.database_type,
            success=success,
            latency_ms=latency_ms,
        )
        return ConnectionTestResponse(success=success, message=message, latency_ms=latency_ms)


connection_service = ConnectionService()
