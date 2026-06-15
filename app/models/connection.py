from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Connection(Base):
    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    database_type: Mapped[str] = mapped_column(String(32), nullable=False)
    connection_method: Mapped[str] = mapped_column(String(16), nullable=False)
    # Encrypted JSON blob — never store plaintext credentials
    connection_data: Mapped[str] = mapped_column(Text, nullable=False)
    # Human label to identify the connection in UI
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Connection id={self.id} type={self.database_type}>"
