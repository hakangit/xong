"""teaching sessions and skill usage events

Revision ID: 005
Revises: 004
Create Date: 2026-08-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, Sequence[str], None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teaching_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("teacher", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("started_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ended_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("first_clean_run_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("corrections", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_ref", sa.Text(), nullable=False, server_default=""),
        sa.Column("confidence_before", sa.Float(), nullable=True),
        sa.Column("confidence_after", sa.Float(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["teacher"], ["org_people.username"]),
    )
    op.create_index("ix_teaching_skill", "teaching_sessions", ["skill_id"])
    op.create_index("ix_teaching_teacher", "teaching_sessions", ["teacher"])

    op.create_table(
        "skill_usage_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("subject_kind", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column(
            "used_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("source_ref", sa.Text(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "subject_kind IN ('person', 'agent')",
            name="ck_skill_usage_events_subject_kind",
        ),
    )
    op.create_index("ix_skill_usage_skill", "skill_usage_events", ["skill_id"])

def downgrade() -> None:
    op.drop_index("ix_skill_usage_skill", table_name="skill_usage_events")
    op.drop_table("skill_usage_events")
    op.drop_index("ix_teaching_teacher", table_name="teaching_sessions")
    op.drop_index("ix_teaching_skill", table_name="teaching_sessions")
    op.drop_table("teaching_sessions")
