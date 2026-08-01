"""decision traces

Revision ID: 006
Revises: 005
Create Date: 2026-08-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, Sequence[str], None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "decision_traces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("situation", sa.Text(), nullable=False),
        sa.Column(
            "options",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("approver", sa.Text(), nullable=True),
        sa.Column("approval", sa.Text(), nullable=False),
        sa.Column(
            "outcome", sa.Text(), nullable=False, server_default="pending"
        ),
        sa.Column("superseded_by", sa.Integer(), nullable=True),
        sa.Column("trust", sa.Float(), nullable=False, server_default="0.3"),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("source_ref", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "search_tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', situation || ' ' || decision)",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["superseded_by"], ["decision_traces.id"]),
        sa.CheckConstraint(
            "kind IN ('decision', 'boundary')",
            name="ck_decision_traces_kind",
        ),
        sa.CheckConstraint(
            "approval IN ('explicit', 'standing_rule', 'corrected')",
            name="ck_decision_traces_approval",
        ),
        sa.CheckConstraint(
            "outcome IN ('pending', 'ok', 'corrected', 'superseded')",
            name="ck_decision_traces_outcome",
        ),
    )
    op.create_index(
        "ix_traces_skill",
        "decision_traces",
        ["skill_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_traces_tsv",
        "decision_traces",
        ["search_tsv"],
        postgresql_using="gin",
    )

def downgrade() -> None:
    op.drop_index("ix_traces_tsv", table_name="decision_traces")
    op.drop_index("ix_traces_skill", table_name="decision_traces")
    op.drop_table("decision_traces")
