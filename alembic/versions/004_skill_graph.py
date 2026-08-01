"""skill graph: aliases, merge, edges, cycle trigger

Revision ID: 004
Revises: 003
Create Date: 2026-08-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, Sequence[str], None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "skills",
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
    )
    op.add_column(
        "skills",
        sa.Column("merged_into_id", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_skills_status",
        "skills",
        "status IN ('active', 'merged', 'retired')",
    )
    op.create_foreign_key(
        "fk_skills_merged_into_id",
        "skills",
        "skills",
        ["merged_into_id"],
        ["id"],
    )

    op.create_table(
        "skill_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
    )
    op.create_index("uq_skill_aliases_alias", "skill_aliases", ["alias"], unique=True)

    op.create_table(
        "skill_edges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("src_skill_id", sa.Integer(), nullable=False),
        sa.Column("dst_skill_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.6"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="proposed"),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["src_skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dst_skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "kind IN ('requires', 'generalizes')",
            name="ck_skill_edges_kind",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_skill_edges_confidence",
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'approved', 'rejected')",
            name="ck_skill_edges_status",
        ),
        sa.UniqueConstraint(
            "src_skill_id",
            "dst_skill_id",
            "kind",
            name="uq_skill_edge",
        ),
        sa.CheckConstraint(
            "src_skill_id <> dst_skill_id",
            name="ck_skill_edge_no_self",
        ),
    )

    # Reject an insert/update that would create a same-kind cycle among
    # non-rejected edges: if NEW.dst can already reach NEW.src, adding
    # NEW.src → NEW.dst closes a cycle.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION skill_edges_reject_cycle()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            would_cycle boolean;
        BEGIN
            IF NEW.src_skill_id = NEW.dst_skill_id THEN
                RAISE EXCEPTION 'skill edge would create a cycle'
                    USING ERRCODE = 'check_violation';
            END IF;

            IF NEW.status = 'rejected' THEN
                RETURN NEW;
            END IF;

            WITH RECURSIVE reach AS (
                SELECT e.dst_skill_id AS node_id,
                       ARRAY[e.src_skill_id, e.dst_skill_id]::int[] AS path
                FROM skill_edges AS e
                WHERE e.src_skill_id = NEW.dst_skill_id
                  AND e.kind = NEW.kind
                  AND e.status <> 'rejected'
                  AND (TG_OP = 'INSERT' OR e.id IS DISTINCT FROM NEW.id)
                UNION ALL
                SELECT e.dst_skill_id,
                       r.path || e.dst_skill_id
                FROM skill_edges AS e
                JOIN reach AS r ON e.src_skill_id = r.node_id
                WHERE e.kind = NEW.kind
                  AND e.status <> 'rejected'
                  AND (TG_OP = 'INSERT' OR e.id IS DISTINCT FROM NEW.id)
                  AND NOT e.dst_skill_id = ANY (r.path)
            )
            SELECT EXISTS (
                SELECT 1 FROM reach WHERE node_id = NEW.src_skill_id
            ) INTO would_cycle;

            IF would_cycle THEN
                RAISE EXCEPTION 'skill edge would create a cycle'
                    USING ERRCODE = 'check_violation';
            END IF;

            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_skill_edges_reject_cycle
        BEFORE INSERT OR UPDATE ON skill_edges
        FOR EACH ROW
        EXECUTE PROCEDURE skill_edges_reject_cycle();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_skill_edges_reject_cycle ON skill_edges")
    op.execute("DROP FUNCTION IF EXISTS skill_edges_reject_cycle()")
    op.drop_table("skill_edges")
    op.drop_index("uq_skill_aliases_alias", table_name="skill_aliases")
    op.drop_table("skill_aliases")
    op.drop_constraint("fk_skills_merged_into_id", "skills", type_="foreignkey")
    op.drop_constraint("ck_skills_status", "skills", type_="check")
    op.drop_column("skills", "merged_into_id")
    op.drop_column("skills", "status")
