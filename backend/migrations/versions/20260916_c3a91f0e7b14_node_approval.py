"""Node approval records.

A human decision is stored on the node so a paused workflow can resume from the
database rather than from whoever clicked the button.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3a91f0e7b14"
down_revision: str | None = "dbec213cc6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_nodes",
        sa.Column("approval", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workflow_nodes", "approval")
