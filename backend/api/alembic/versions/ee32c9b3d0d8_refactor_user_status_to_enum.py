"""refactor user status to enum

Revision ID: ee32c9b3d0d8
Revises: 97fd688f2d9a
Create Date: 2026-04-02 22:28:09.298679

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ee32c9b3d0d8"
down_revision: str | Sequence[str] | None = "97fd688f2d9a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    user_status_enum = sa.Enum(
        "ACTIVE", "INACTIVE", "BANNED", "ANONYMIZED", name="userstatus"
    )
    user_status_enum.create(op.get_bind())

    op.add_column(
        "users",
        sa.Column(
            "status",
            user_status_enum,
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
    )
    op.drop_column("users", "is_anonymized")
    op.drop_column("users", "is_active")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.BOOLEAN(),
            autoincrement=False,
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_anonymized",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=False,
        ),
    )
    op.drop_column("users", "status")

    user_status_enum = sa.Enum(
        "ACTIVE", "INACTIVE", "BANNED", "ANONYMIZED", name="userstatus"
    )
    user_status_enum.drop(op.get_bind())
