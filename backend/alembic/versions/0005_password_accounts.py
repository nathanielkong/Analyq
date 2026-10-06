"""Allow local username/password accounts alongside Google."""

import sqlalchemy as sa
from alembic import op

revision = "0005_password_accounts"
down_revision = "0004_daily_research_cache"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("users", "google_subject", nullable=True)
    op.alter_column("users", "email", nullable=True)
    op.add_column("users", sa.Column("username", sa.String(32), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_users_username", "users", ["username"])


def downgrade():
    # Local-only accounts must be migrated before reinstating Google-only columns.
    op.alter_column("users", "google_subject", nullable=False)
    op.alter_column("users", "email", nullable=False)
    op.drop_constraint("uq_users_username", "users", type_="unique")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")
