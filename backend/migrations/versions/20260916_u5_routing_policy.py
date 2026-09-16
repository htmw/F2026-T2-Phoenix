"""Add routing_policy for provider priority and blocked models.

Revision id: u5_routing_policy
Revises: u2_provider_connections
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "u5_routing_policy"
down_revision: Union[str, Sequence[str], None] = "u2_provider_connections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "routing_policy",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column(
            "provider_priority",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "blocked_models",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO routing_policy (id, provider_priority, blocked_models) "
            "VALUES ('default', '[]'::jsonb, '[]'::jsonb)"
        )
    )


def downgrade() -> None:
    op.drop_table("routing_policy")
