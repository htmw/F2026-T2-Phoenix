"""conditional workflows and cancellation

Adds the state that conditional execution, feedback loops, and cancellation need:
a node's join policy and feedback rule, and a workflow's cancellation request.

The two NOT NULL columns carry a server default so the migration succeeds on a table
that already holds workflows — without it, this fails on any environment that has run a
single task.

Revision ID: dbec213cc6d7
Revises: 55e2af3bf22e
Create Date: 2026-09-15 20:14:17.555716
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "dbec213cc6d7"
down_revision: str | None = "55e2af3bf22e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_nodes",
        sa.Column("join_policy", sa.String(length=8), nullable=False, server_default="all"),
    )
    op.add_column(
        "workflow_nodes",
        sa.Column("feedback", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "workflows",
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("workflows", "cancel_requested")
    op.drop_column("workflow_nodes", "feedback")
    op.drop_column("workflow_nodes", "join_policy")
