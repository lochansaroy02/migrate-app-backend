from fastapi import APIRouter, Body

from app.schemas.connection import ConnectionTestRequest, ConnectionTestResponse
from app.services.connection_service import connection_service

router = APIRouter(prefix="/connections", tags=["connections"])


@router.post(
    "/test",
    response_model=ConnectionTestResponse,
    summary="Test a database connection",
)
async def test_connection(
    req: ConnectionTestRequest = Body(...),
) -> ConnectionTestResponse:
    """
    Test connectivity to a source or destination database.
    Accepts either a database URL or individual credentials.
    """
    return await connection_service.test_connection(req)
