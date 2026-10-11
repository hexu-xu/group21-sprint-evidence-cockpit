"""Add task module for the story map.

Revision ID: 9e7a2b4c6d10
Revises: 39527eb94179
"""

from alembic import op
import sqlalchemy as sa


revision = "9e7a2b4c6d10"
down_revision = "39527eb94179"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column(
            "module_name", sa.String(length=60), nullable=False,
            server_default="未分类",
        ))


def downgrade():
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_column("module_name")
