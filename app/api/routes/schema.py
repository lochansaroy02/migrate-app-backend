from fastapi import APIRouter, Body

from app.schemas.connection import ConnectionCredentials, SchemaResponse
from app.services.schema_service import schema_service

router = APIRouter(prefix="/schema", tags=["schema"])


@router.post(
    "/tables",
    response_model=SchemaResponse,
    summary="Discover tables and row counts",
)
async def get_tables(
    connection: ConnectionCredentials = Body(...),
) -> SchemaResponse:
    """
    Connect to a database and return the list of tables with approximate row counts.
    Accepts the same connection credential format as the connection test endpoint.
    """
    return await schema_service.get_tables(connection)
