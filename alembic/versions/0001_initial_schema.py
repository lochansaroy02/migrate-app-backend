"""Initial schema — connections, migrations, migration_logs

Revision ID: 0001
Revises:
Create Date: 2026-06-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("database_type", sa.String(32), nullable=False),
        sa.Column("connection_method", sa.String(16), nullable=False),
        sa.Column("connection_data", sa.Text, nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "migrations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False, default="pending"),
        sa.Column("source_connection", sa.Text, nullable=False),
        sa.Column("destination_connection", sa.Text, nullable=False),
        sa.Column("tables_config", sa.Text, nullable=True),
        sa.Column("migration_plan", sa.Text, nullable=True),
        sa.Column("settings", sa.Text, nullable=True),
        sa.Column("total_tables", sa.Integer, nullable=False, default=0),
        sa.Column("completed_tables", sa.Integer, nullable=False, default=0),
        sa.Column("total_rows", sa.BigInteger, nullable=False, default=0),
        sa.Column("processed_rows", sa.BigInteger, nullable=False, default=0),
        sa.Column("current_table", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index("ix_migrations_status", "migrations", ["status"])

    op.create_table(
        "migration_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("migration_id", sa.String(36), nullable=False, index=True),
        sa.Column("level", sa.String(16), nullable=False, default="INFO"),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("table_name", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_migration_logs_migration_created",
        "migration_logs",
        ["migration_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_migration_logs_migration_created", table_name="migration_logs")
    op.drop_table("migration_logs")
    op.drop_index("ix_migrations_status", table_name="migrations")
    op.drop_table("migrations")
    op.drop_table("connections")
