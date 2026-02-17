"""create shares table

Revision ID: 001
Revises:
Create Date: 2026-02-17
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shares",
        sa.Column("share_id", sa.String(16), primary_key=True),
        sa.Column("device_id", sa.String(128), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("click_count", sa.Integer, default=0, nullable=False),
        sa.Column("max_clicks", sa.Integer, default=50, nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "deleted", "failed", name="sharestatus"),
            default="active",
            nullable=False,
            index=True,
        ),
        sa.Column("ai_audio_key", sa.String(256), nullable=True),
        sa.Column("lang", sa.String(8), nullable=True),
        sa.Column("region", sa.String(32), nullable=True),
        sa.Column("platform", sa.String(32), nullable=True),
        sa.Column("script_version", sa.String(16), nullable=True),
    )


def downgrade():
    op.drop_table("shares")
    op.execute("DROP TYPE IF EXISTS sharestatus")
