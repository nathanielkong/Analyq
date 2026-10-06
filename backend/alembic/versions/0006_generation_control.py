"""Durable cooperative cancellation across API workers."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "0006_generation_control"
down_revision = "0005_password_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "generation_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_generation_requests_session_id", "generation_requests", ["session_id"]
    )


def downgrade():
    op.drop_table("generation_requests")
