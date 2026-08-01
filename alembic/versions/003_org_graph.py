"""organization graph and skills knowledge layer

Revision ID: 003
Revises: 002
Create Date: 2026-08-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, Sequence[str], None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "org_people",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("department_raw", sa.Text(), nullable=True),
        sa.Column("site", sa.Text(), nullable=True),
        sa.Column("manager_username", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "synced_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "site IS NULL OR site IN ('MS', 'HS', 'JM', 'MD')",
            name="ck_org_people_site",
        ),
    )
    op.create_index("ix_org_people_username", "org_people", ["username"], unique=True)
    op.create_index("ix_org_people_department", "org_people", ["department"])
    op.create_index("ix_org_people_site", "org_people", ["site"])
    op.create_index("ix_org_people_manager_username", "org_people", ["manager_username"])

    op.create_table(
        "skills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_skills_slug", "skills", ["slug"], unique=True)

    op.create_table(
        "skill_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("subject_kind", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.6"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "subject_kind IN ('person', 'agent')",
            name="ck_skill_claims_subject_kind",
        ),
        sa.CheckConstraint(
            "kind IN ('can_do', 'knows_about', 'owns_process')",
            name="ck_skill_claims_kind",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_skill_claims_confidence",
        ),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "skill_id",
            "subject_kind",
            "subject",
            "kind",
            name="uq_skill_claim_subject",
        ),
    )


def downgrade() -> None:
    op.drop_table("skill_claims")
    op.drop_index("ix_skills_slug", table_name="skills")
    op.drop_table("skills")
    op.drop_index("ix_org_people_manager_username", table_name="org_people")
    op.drop_index("ix_org_people_site", table_name="org_people")
    op.drop_index("ix_org_people_department", table_name="org_people")
    op.drop_index("ix_org_people_username", table_name="org_people")
    op.drop_table("org_people")
