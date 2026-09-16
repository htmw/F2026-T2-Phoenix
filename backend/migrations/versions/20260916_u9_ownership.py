"""Add owner_id to tasks and workflows (auth foundations).

Revision ID: 20260916_u9_ownership
Revises: 20260916_u7_decision_log
Create Date: 2026-09-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260916_u9_ownership"
down_revision: str | None = "u7_decision_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("owner_id", sa.String(length=64), nullable=False, server_default="operator"),
    )
    op.add_column(
        "workflows",
        sa.Column("owner_id", sa.String(length=64), nullable=False, server_default="operator"),
    )
    op.create_index("ix_workflows_owner_id", "workflows", ["owner_id"])
    op.create_index("ix_tasks_owner_id", "tasks", ["owner_id"])
    # Drop server defaults so inserts must set ownership explicitly going forward.
    op.alter_column("tasks", "owner_id", server_default=None)
    op.alter_column("workflows", "owner_id", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_tasks_owner_id", table_name="tasks")
    op.drop_index("ix_workflows_owner_id", table_name="workflows")
    op.drop_column("workflows", "owner_id")
    op.drop_column("tasks", "owner_id")
