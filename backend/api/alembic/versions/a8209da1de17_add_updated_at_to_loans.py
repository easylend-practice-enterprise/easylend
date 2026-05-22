"""add updated_at to loans

Revision ID: a8209da1de17
Revises: b3e1f42c9d7a
Create Date: 2026-05-22 13:00:52.681562

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8209da1de17"
down_revision: str | Sequence[str] | None = "b3e1f42c9d7a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "loans",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("loans", "updated_at")
