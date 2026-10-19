"""Agent enrollment: declared models, per-agent result tables, unique names.

Revision ID: u12_agent_enrollment
Revises: u11_users_and_files
Create Date: 2026-10-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "u12_agent_enrollment"
down_revision: str | None = "u11_users_and_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "supported_models",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("agents", sa.Column("table_name", sa.String(length=63), nullable=True))
    op.create_index("uq_agents_name_lower", "agents", [sa.text("lower(name)")], unique=True)
    # Per-agent tables are created at enrollment time, outside migrations, so they live
    # in their own schema and never collide with or show up among the core tables.
    op.execute("CREATE SCHEMA IF NOT EXISTS agent_data")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS agent_data CASCADE")
    op.drop_index("uq_agents_name_lower", table_name="agents")
    op.drop_column("agents", "table_name")
    op.drop_column("agents", "supported_models")
