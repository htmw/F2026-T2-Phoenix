"""Add decision_records for the office decision log.

Revision id: u7_decision_log
Revises: u5_routing_policy
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "u7_decision_log"
down_revision: Union[str, Sequence[str], None] = "u5_routing_policy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "decision_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=True),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("node_key", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decision_records_workflow", "decision_records", ["workflow_id"])
    op.create_index("ix_decision_records_agent", "decision_records", ["agent_id"])
    op.create_index("ix_decision_records_kind", "decision_records", ["kind"])
    op.create_index("ix_decision_records_expires", "decision_records", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_decision_records_expires", table_name="decision_records")
    op.drop_index("ix_decision_records_kind", table_name="decision_records")
    op.drop_index("ix_decision_records_agent", table_name="decision_records")
    op.drop_index("ix_decision_records_workflow", table_name="decision_records")
    op.drop_table("decision_records")
