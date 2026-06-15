from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MigrationLog(Base):
    __tablename__ = "migration_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    migration_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="INFO")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    table_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_migration_logs_migration_created", "migration_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<MigrationLog migration={self.migration_id} level={self.level}>"
