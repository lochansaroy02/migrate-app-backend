"""
Schema discovery service — reads table list and metadata from a live database.
"""

from app.providers import get_provider
from app.schemas.connection import ConnectionCredentials, SchemaResponse, TableInfo
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _creds_to_dict(conn: ConnectionCredentials) -> dict:
    return {k: v for k, v in conn.model_dump().items() if v is not None}


class SchemaService:
    async def get_tables(self, connection: ConnectionCredentials) -> SchemaResponse:
        creds = _creds_to_dict(connection)
        provider = get_provider(connection.database_type.value, creds)

        async with provider:
            table_names = await provider.get_tables()
            tables: list[TableInfo] = []
            for name in table_names:
                try:
                    count = await provider.get_row_count(name)
                except Exception as exc:
                    logger.warning("Could not count rows", table=name, error=str(exc))
                    count = -1
                tables.append(TableInfo(name=name, rows=count))

        return SchemaResponse(
            tables=tables,
            database_type=connection.database_type.value,
        )


schema_service = SchemaService()
