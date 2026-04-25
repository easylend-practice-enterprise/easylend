"""add server default to user status

Revision ID: b3e1f42c9d7a
Revises: ee32c9b3d0d8
Create Date: 2026-04-07 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3e1f42c9d7a"
down_revision: str | Sequence[str] | None = "ee32c9b3d0d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "users",
        "status",
        existing_type=sa.Enum(
            "ACTIVE",
            "INACTIVE",
            "BANNED",
            "ANONYMIZED",
            name="userstatus",
        ),
        server_default=sa.text("'ACTIVE'"),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "users",
        "status",
        existing_type=sa.Enum(
            "ACTIVE",
            "INACTIVE",
            "BANNED",
            "ANONYMIZED",
            name="userstatus",
        ),
        server_default=None,
        existing_nullable=False,
    )
