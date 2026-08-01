"""attachments (files on persistent storage + url links)

Revision ID: 002
Revises: 001
Create Date: 2026-07-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("filename", sa.String(512), nullable=True),
        sa.Column("content_type", sa.String(255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("storage_path", sa.String(1024), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_attachments_task_id", "attachments", ["task_id"])
    op.create_index("ix_attachments_owner_id", "attachments", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_attachments_owner_id", table_name="attachments")
    op.drop_index("ix_attachments_task_id", table_name="attachments")
    op.drop_table("attachments")
