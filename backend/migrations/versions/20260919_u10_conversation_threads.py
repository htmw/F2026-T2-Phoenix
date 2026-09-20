"""Add parent_workflow_id to workflows (continuous chat / conversation threads).

Revision ID: 20260919_u10_conversation_threads
Revises: 20260916_u9_ownership
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "u10_conversation_threads"
down_revision: str | None = "20260916_u9_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflows",
        sa.Column("parent_workflow_id", sa.Uuid(), nullable=True),
    )
    # SET NULL, not CASCADE: pruning one turn of a conversation must not delete the
    # turns that continued from it.
    op.create_foreign_key(
        "fk_workflows_parent",
        "workflows",
        "workflows",
        ["parent_workflow_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_workflows_parent", "workflows", ["parent_workflow_id"])


def downgrade() -> None:
    op.drop_index("ix_workflows_parent", table_name="workflows")
    op.drop_constraint("fk_workflows_parent", "workflows", type_="foreignkey")
    op.drop_column("workflows", "parent_workflow_id")
