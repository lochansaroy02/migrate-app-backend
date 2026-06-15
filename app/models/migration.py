from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Migration(Base):
    __tablename__ = "migrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")

    # Stored as encrypted JSON blobs (same format as Connection.connection_data)
    source_connection: Mapped[str] = mapped_column(Text, nullable=False)
    destination_connection: Mapped[str] = mapped_column(Text, nullable=False)

    # Serialised JSON: list of table names and the migration plan
    tables_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    migration_plan: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Settings JSON blob (batch_size, include_schema, include_data, …)
    settings: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Progress counters
    total_tables: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_tables: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_rows: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    processed_rows: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    current_table: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Timing
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Celery task ID for cancellation / status lookup
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Human-readable error summary when status = "failed"
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Migration id={self.id} status={self.status}>"
