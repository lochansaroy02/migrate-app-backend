"""
Provider registry — maps DatabaseType → provider class.
Adding a new database only requires:
  1. Creating a new provider module that subclasses BaseDatabaseProvider.
  2. Registering it in PROVIDER_REGISTRY below.
No migration logic needs to change.
"""

from app.core.constants import DatabaseType
from app.providers.base_provider import BaseDatabaseProvider
from app.providers.mysql_provider import MySQLProvider
from app.providers.postgres_provider import PostgresProvider
from app.providers.sqlite_provider import SQLiteProvider

PROVIDER_REGISTRY: dict[DatabaseType, type[BaseDatabaseProvider]] = {
    DatabaseType.POSTGRES: PostgresProvider,
    DatabaseType.MYSQL: MySQLProvider,
    DatabaseType.SQLITE: SQLiteProvider,
}


def get_provider(database_type: str, credentials: dict) -> BaseDatabaseProvider:
    """Factory that resolves and instantiates the correct provider."""
    dtype = DatabaseType(database_type)
    provider_cls = PROVIDER_REGISTRY.get(dtype)
    if provider_cls is None:
        raise NotImplementedError(
            f"Database type '{database_type}' is not yet supported. "
            f"Supported types: {[t.value for t in PROVIDER_REGISTRY]}"
        )
    return provider_cls(credentials)


__all__ = [
    "BaseDatabaseProvider",
    "PostgresProvider",
    "MySQLProvider",
    "SQLiteProvider",
    "PROVIDER_REGISTRY",
    "get_provider",
]
