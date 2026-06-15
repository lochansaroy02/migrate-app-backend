from enum import Enum


class DatabaseType(str, Enum):
    POSTGRES = "postgres"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    # Future support — registered but not yet implemented
    MSSQL = "mssql"
    MONGODB = "mongodb"
    ORACLE = "oracle"
    MARIADB = "mariadb"


class ConnectionMethod(str, Enum):
    URL = "url"
    CREDENTIALS = "credentials"


class MigrationStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# Default DB ports
DEFAULT_PORTS: dict[str, int] = {
    DatabaseType.POSTGRES: 5432,
    DatabaseType.MYSQL: 3306,
    DatabaseType.MSSQL: 1433,
    DatabaseType.MARIADB: 3306,
    DatabaseType.ORACLE: 1521,
}

# Type affinity maps used by the mapper module
# Maps (source_type_prefix -> universal_type)
TYPE_AFFINITY: dict[str, str] = {
    # Integers
    "int": "INTEGER",
    "tinyint": "SMALLINT",
    "smallint": "SMALLINT",
    "mediumint": "INTEGER",
    "bigint": "BIGINT",
    "serial": "INTEGER",
    "bigserial": "BIGINT",
    # Floats
    "float": "FLOAT",
    "double": "DOUBLE",
    "real": "FLOAT",
    "decimal": "DECIMAL",
    "numeric": "DECIMAL",
    "money": "DECIMAL",
    # Strings
    "char": "CHAR",
    "varchar": "VARCHAR",
    "text": "TEXT",
    "tinytext": "TEXT",
    "mediumtext": "TEXT",
    "longtext": "TEXT",
    "nchar": "CHAR",
    "nvarchar": "VARCHAR",
    "ntext": "TEXT",
    # Binary
    "blob": "BLOB",
    "tinyblob": "BLOB",
    "mediumblob": "BLOB",
    "longblob": "BLOB",
    "bytea": "BLOB",
    "binary": "BLOB",
    "varbinary": "BLOB",
    # Date / Time
    "date": "DATE",
    "time": "TIME",
    "datetime": "DATETIME",
    "timestamp": "TIMESTAMP",
    "year": "SMALLINT",
    "interval": "VARCHAR",
    # Boolean
    "bool": "BOOLEAN",
    "boolean": "BOOLEAN",
    "bit": "BOOLEAN",
    # JSON / semi-structured
    "json": "JSON",
    "jsonb": "JSON",
    # UUID
    "uuid": "VARCHAR",
    # Misc
    "enum": "VARCHAR",
    "set": "VARCHAR",
}
