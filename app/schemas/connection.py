from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.constants import ConnectionMethod, DatabaseType


class ConnectionCredentials(BaseModel):
    """Raw credentials — never stored in this form; always encrypted."""

    database_type: DatabaseType
    connection_method: ConnectionMethod

    # URL-based
    database_url: str | None = None

    # Credentials-based
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None

    # Optional for SQLite
    file_path: str | None = None

    @model_validator(mode="after")
    def validate_fields_for_method(self) -> "ConnectionCredentials":
        if self.connection_method == ConnectionMethod.URL:
            if not self.database_url:
                raise ValueError("database_url is required when connection_method is 'url'")
        elif self.connection_method == ConnectionMethod.CREDENTIALS:
            if self.database_type == DatabaseType.SQLITE:
                if not self.file_path:
                    raise ValueError("file_path is required for SQLite credential connections")
            else:
                missing = [
                    f for f in ["host", "database", "username", "password"]
                    if not getattr(self, f)
                ]
                if missing:
                    raise ValueError(f"Missing required credential fields: {', '.join(missing)}")
        return self

    @field_validator("port", mode="before")
    @classmethod
    def validate_port(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 65535):
            raise ValueError("port must be between 1 and 65535")
        return v


class ConnectionTestRequest(ConnectionCredentials):
    """Request body for POST /api/connections/test"""


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str
    latency_ms: float | None = None


class TableInfo(BaseModel):
    name: str
    rows: int
    schema_name: str | None = None


class SchemaResponse(BaseModel):
    tables: list[TableInfo]
    database_type: str
