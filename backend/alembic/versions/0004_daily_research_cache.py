"""Daily account-scoped research reuse and report expiry."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "0004_daily_research_cache"
down_revision = "0003_saved_research_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_reports", sa.Column("expires_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "research_reports",
        sa.Column("format_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "daily_research_cache",
        sa.Column("scope", sa.String(50), primary_key=True),
        sa.Column("symbol", sa.String(30), primary_key=True),
        sa.Column("research", postgresql.JSONB(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("format_version", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_daily_research_cache_expires_at", "daily_research_cache", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_table("daily_research_cache")
    op.drop_column("research_reports", "format_version")
    op.drop_column("research_reports", "expires_at")
