"""Preserve baseline metadata and checkpoint revisions.

Revision ID: c4e7b1d95a20
Revises: ab42c7d39e51
"""

from alembic import op
import sqlalchemy as sa


revision = "c4e7b1d95a20"
down_revision = "ab42c7d39e51"
branch_labels = None
depends_on = None


def upgrade():
    # Existing candidate data has no trustworthy original baseline metadata.
    # Leave it unknown rather than inferring a compilation date from updated_at.
    with op.batch_alter_table("project_progress_checkpoints") as batch:
        batch.add_column(sa.Column("baseline_version", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("baseline_established_on", sa.Date(), nullable=True))
    op.create_table(
        "project_progress_checkpoint_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("checkpoint_id", sa.Integer(), sa.ForeignKey("project_progress_checkpoints.id"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("old_target_date", sa.Date(), nullable=True),
        sa.Column("new_target_date", sa.Date(), nullable=False),
        sa.Column("old_planned_count", sa.Integer(), nullable=True),
        sa.Column("new_planned_count", sa.Integer(), nullable=False),
        sa.Column("old_actual_count", sa.Integer(), nullable=True),
        sa.Column("new_actual_count", sa.Integer(), nullable=True),
        sa.Column("old_actual_evidence", sa.String(length=255), nullable=True),
        sa.Column("new_actual_evidence", sa.String(length=255), nullable=False),
        sa.Column("old_baseline_version", sa.String(length=32), nullable=True),
        sa.Column("new_baseline_version", sa.String(length=32), nullable=False),
        sa.Column("old_baseline_established_on", sa.Date(), nullable=True),
        sa.Column("new_baseline_established_on", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_progress_revisions_project", "project_progress_checkpoint_revisions",
                    ["project_id", "changed_at"])


def downgrade():
    op.drop_index("ix_progress_revisions_project", table_name="project_progress_checkpoint_revisions")
    op.drop_table("project_progress_checkpoint_revisions")
    with op.batch_alter_table("project_progress_checkpoints") as batch:
        batch.drop_column("baseline_established_on")
        batch.drop_column("baseline_version")
