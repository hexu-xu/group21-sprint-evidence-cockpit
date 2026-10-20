"""Add cumulative project story checkpoints.

Revision ID: ab42c7d39e51
Revises: 9e7a2b4c6d10
"""

from alembic import op
import sqlalchemy as sa


revision = "ab42c7d39e51"
down_revision = "9e7a2b4c6d10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_progress_checkpoints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("planned_count", sa.Integer(), nullable=False),
        sa.Column("actual_count", sa.Integer(), nullable=True),
        sa.Column("actual_evidence", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.current_timestamp()),
        sa.CheckConstraint("planned_count >= 0", name="progress_planned_nonnegative"),
        sa.CheckConstraint("actual_count IS NULL OR actual_count >= 0", name="progress_actual_nonnegative"),
        sa.UniqueConstraint("project_id", "target_date"),
    )


def downgrade():
    op.drop_table("project_progress_checkpoints")
