"""Users, operator-scoped memory, and artifact owners.

Revision ID: u11_users_and_files
Revises: u10_conversation_threads
Create Date: 2026-10-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "u11_users_and_files"
down_revision: str | None = "u10_conversation_threads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("google_sub", sa.String(length=64), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_name", sa.String(length=240), nullable=True),
        sa.Column("picture_url", sa.String(length=2000), nullable=True),
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("uq_users_email", "users", ["email"], unique=True)
    op.add_column("memories", sa.Column("operator_id", sa.String(length=64), nullable=True))
    op.create_index("ix_memories_operator_visibility", "memories", ["operator_id", "visibility"])
    op.add_column("artifacts", sa.Column("owner_id", sa.String(length=64), nullable=True))
    op.create_index("ix_artifacts_owner_id", "artifacts", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_artifacts_owner_id", table_name="artifacts")
    op.drop_column("artifacts", "owner_id")
    op.drop_index("ix_memories_operator_visibility", table_name="memories")
    op.drop_column("memories", "operator_id")
    op.drop_index("uq_users_email", table_name="users")
    op.drop_table("users")
