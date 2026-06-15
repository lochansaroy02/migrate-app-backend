from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.core.constants import LogLevel, MigrationStatus
from app.schemas.connection import ConnectionCredentials


class MigrationSettings(BaseModel):
    include_schema: bool = True
    include_data: bool = True
    batch_size: int = Field(default=1000, ge=100, le=50000)
    truncate_destination: bool = False
    continue_on_error: bool = False
    max_retries: int = Field(default=3, ge=0, le=10)


class MigrationCreateRequest(BaseModel):
    source: ConnectionCredentials
    destination: ConnectionCredentials
    tables: list[str] = Field(..., min_length=1)
    settings: MigrationSettings = Field(default_factory=MigrationSettings)

    @field_validator("tables")
    @classmethod
    def tables_not_empty(cls, v: list[str]) -> list[str]:
        cleaned = [t.strip() for t in v if t.strip()]
        if not cleaned:
            raise ValueError("At least one table name must be provided")
        return cleaned


class MigrationCreateResponse(BaseModel):
    migration_id: str


# ── Column / table schema used inside the migration plan ─────────────────────

class ColumnSchema(BaseModel):
    name: str
    data_type: str
    is_nullable: bool = True
    is_primary_key: bool = False
    default: str | None = None
    max_length: int | None = None
    precision: int | None = None
    scale: int | None = None
    enum_values: list[str] | None = None  # populated for PostgreSQL enum columns


class TableSchema(BaseModel):
    name: str
    columns: list[ColumnSchema]
    primary_keys: list[str] = []
    row_count: int = 0


class MigrationTablePlan(BaseModel):
    table_name: str
    source_schema: TableSchema
    destination_schema: TableSchema | None = None
    column_mappings: list[dict] = []
    row_count: int = 0
    status: str = "pending"


class MigrationPlan(BaseModel):
    tables: list[MigrationTablePlan]
    total_rows: int
    warnings: list[str] = []


# ── Status / progress ─────────────────────────────────────────────────────────

class MigrationStatusResponse(BaseModel):
    id: str
    status: MigrationStatus
    progress: int = Field(ge=0, le=100)
    current_table: str | None = None
    processed_rows: int
    total_rows: int
    speed: int = 0
    estimated_time_remaining: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None


class MigrationLogEntry(BaseModel):
    id: str
    timestamp: datetime
    level: LogLevel
    message: str
    table_name: str | None = None


class MigrationLogsResponse(BaseModel):
    migration_id: str
    logs: list[MigrationLogEntry]
    total: int
