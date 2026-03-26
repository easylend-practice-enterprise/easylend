"""update ai_evaluation model for step 10b

Revision ID: 4cc16e6cd3f1
Revises: 5591d67e520a
Create Date: 2026-03-26 22:30:05.829861

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4cc16e6cd3f1"
down_revision: str | Sequence[str] | None = "5591d67e520a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add non-nullable columns with temporary server defaults so migration works
    # when ai_evaluations already contains rows.
    op.add_column(
        "ai_evaluations",
        sa.Column(
            "outcome",
            sa.String(length=100),
            nullable=False,
            server_default="UNKNOWN",
        ),
    )
    op.add_column(
        "ai_evaluations",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Remove defaults to match ORM intent (application-managed values).
    op.alter_column("ai_evaluations", "outcome", server_default=None)
    op.alter_column("ai_evaluations", "created_at", server_default=None)

    op.drop_column("ai_evaluations", "ai_confidence")
    op.drop_column("ai_evaluations", "rejection_reason")
    op.drop_column("ai_evaluations", "has_damage_detected")
    op.drop_column("ai_evaluations", "analyzed_at")
    op.drop_column("ai_evaluations", "detected_objects")
    op.drop_column("ai_evaluations", "is_approved")
    op.drop_column("ai_evaluations", "model_version")
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # Recreate dropped non-null columns with temporary defaults so downgrade also
    # succeeds when ai_evaluations is non-empty.
    op.add_column(
        "ai_evaluations",
        sa.Column(
            "model_version",
            sa.VARCHAR(length=50),
            autoincrement=False,
            nullable=False,
            server_default="legacy",
        ),
    )
    op.add_column(
        "ai_evaluations",
        sa.Column("is_approved", sa.BOOLEAN(), autoincrement=False, nullable=True),
    )
    op.add_column(
        "ai_evaluations",
        sa.Column(
            "detected_objects",
            postgresql.JSONB(astext_type=sa.Text()),
            autoincrement=False,
            nullable=True,
        ),
    )
    op.add_column(
        "ai_evaluations",
        sa.Column(
            "analyzed_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "ai_evaluations",
        sa.Column(
            "has_damage_detected",
            sa.BOOLEAN(),
            autoincrement=False,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "ai_evaluations",
        sa.Column(
            "rejection_reason",
            sa.VARCHAR(length=255),
            autoincrement=False,
            nullable=True,
        ),
    )
    op.add_column(
        "ai_evaluations",
        sa.Column(
            "ai_confidence",
            sa.DOUBLE_PRECISION(precision=53),
            autoincrement=False,
            nullable=False,
            server_default="0",
        ),
    )

    op.alter_column("ai_evaluations", "model_version", server_default=None)
    op.alter_column("ai_evaluations", "analyzed_at", server_default=None)
    op.alter_column("ai_evaluations", "has_damage_detected", server_default=None)
    op.alter_column("ai_evaluations", "ai_confidence", server_default=None)

    op.drop_column("ai_evaluations", "created_at")
    op.drop_column("ai_evaluations", "outcome")
