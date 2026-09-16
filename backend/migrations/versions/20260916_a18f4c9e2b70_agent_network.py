"""Agent network: mailboxes, memory, artifacts, and the append-only event log.

Messages, memories, and artifacts persist independently of a running workflow so an
agent's inbox survives a restart. Presence is overwritten in place.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a18f4c9e2b70"
down_revision: str | None = "c3a91f0e7b14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_id", sa.String(length=64), nullable=False),
        sa.Column("recipient_id", sa.String(length=64), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("node_key", sa.String(length=64), nullable=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("requires_response", sa.Boolean(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["parent_id"], ["agent_messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_messages_recipient_status", "agent_messages", ["recipient_id", "status"]
    )
    op.create_index("ix_agent_messages_sender", "agent_messages", ["sender_id"])
    op.create_index("ix_agent_messages_workflow", "agent_messages", ["workflow_id"])

    op.create_table(
        "agent_presence",
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("current_task", sa.Text(), nullable=True),
        sa.Column("waiting_for", sa.String(length=64), nullable=True),
        sa.Column("sending_to", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("agent_id"),
    )

    op.create_table(
        "memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("owner_agent_id", sa.String(length=64), nullable=True),
        sa.Column("source_agent_id", sa.String(length=64), nullable=True),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memories_owner_visibility", "memories", ["owner_agent_id", "visibility"])
    op.create_index("ix_memories_workflow", "memories", ["workflow_id"])

    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_artifacts_created_by", "artifacts", ["created_by"])

    op.create_table(
        "network_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_network_events_workflow_created", "network_events", ["workflow_id", "created_at"]
    )
    op.create_index("ix_network_events_type", "network_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_network_events_type", table_name="network_events")
    op.drop_index("ix_network_events_workflow_created", table_name="network_events")
    op.drop_table("network_events")
    op.drop_index("ix_artifacts_created_by", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_memories_workflow", table_name="memories")
    op.drop_index("ix_memories_owner_visibility", table_name="memories")
    op.drop_table("memories")
    op.drop_table("agent_presence")
    op.drop_index("ix_agent_messages_workflow", table_name="agent_messages")
    op.drop_index("ix_agent_messages_sender", table_name="agent_messages")
    op.drop_index("ix_agent_messages_recipient_status", table_name="agent_messages")
    op.drop_table("agent_messages")
