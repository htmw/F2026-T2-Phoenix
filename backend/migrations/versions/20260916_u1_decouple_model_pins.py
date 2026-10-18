"""Clear hard-coded vendor model pins from seeded agent preferences.

Revision id: u1_decouple_model_pins
Revises: a18f4c9e2b70
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "u1_decouple_model_pins"
down_revision: str | Sequence[str] | None = "a18f4c9e2b70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE agents
            SET model_preference = (model_preference - 'preferred_model' - 'preferred_provider')
            WHERE model_preference ? 'preferred_model'
               OR model_preference ? 'preferred_provider'
            """
        )
    )


def downgrade() -> None:
    pass
