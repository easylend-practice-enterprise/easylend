"""add_returning_to_loan_status

Revision ID: 5591d67e520a
Revises: aac5afd64c4c
Create Date: 2026-03-18 21:50:47.161421

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5591d67e520a"
down_revision: str | Sequence[str] | None = "aac5afd64c4c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE loanstatus ADD VALUE IF NOT EXISTS 'RETURNING'")


def downgrade() -> None:
    """Downgrade schema.

    This migration adds a new value to the PostgreSQL ``loanstatus`` enum
    type using ``ALTER TYPE ... ADD VALUE`` which is not trivially
    reversible. Removing enum labels in PostgreSQL is unsafe for existing
    data and requires manual intervention, so this downgrade is
    intentionally not implemented.
    """
    raise NotImplementedError(
        "Downgrade for migration 5591d67e520a is not supported because "
        "removing values from the 'loanstatus' enum requires manual "
        "operations and may be unsafe for existing data."
    )
