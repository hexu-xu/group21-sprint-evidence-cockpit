"""Add named user roles and task progress notes.

Revision ID: d10e6f4a21bc
Revises: c4e7b1d95a20
"""

from alembic import op
import sqlalchemy as sa

revision = "d10e6f4a21bc"
down_revision = "c4e7b1d95a20"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("platform_role", sa.String(30), nullable=False),
    )
    # SQLite can add a nullable REFERENCES column directly while foreign keys are on;
    # Alembic's batch table rebuild would fail because existing tables reference users.
    op.execute("ALTER TABLE users ADD COLUMN role_id INTEGER REFERENCES user_roles(id)")
    op.create_table(
        "task_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_task_comments_task_id", "task_comments", ["task_id"])


def downgrade():
    op.drop_index("ix_task_comments_task_id", table_name="task_comments")
    op.drop_table("task_comments")
    op.execute("ALTER TABLE users DROP COLUMN role_id")
    op.drop_table("user_roles")
