"""excel semantic layer: logical fields, managed files, bindings, fingerprints

PROVISIONAL REVISION NUMBER. This branch was cut from origin/main at head 005.
Task 3 (decision traces) also claims 006 and merges first; renumber this
revision (file name, `revision`, `down_revision`) to 007 before merging so the
chain stays linear and `alembic heads` reports exactly one head.

Revision ID: 006
Revises: 005
Create Date: 2026-08-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, Sequence[str], None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "logical_fields",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("concept_key", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("datatype", sa.Text(), nullable=False),
        sa.Column(
            "table_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("parse_rule", sa.Text(), nullable=True),
        sa.Column("unique_in_sheet", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Text(), nullable=False),
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
        sa.UniqueConstraint("concept_key", name="uq_logical_fields_concept_key"),
        sa.CheckConstraint(
            "datatype IN ('string', 'number', 'integer', 'boolean', 'date', 'datetime', 'any')",
            name="ck_logical_fields_datatype",
        ),
    )

    op.create_table(
        "managed_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("sheet_name", sa.Text(), nullable=False),
        sa.Column("header_row", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_data_row", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("owner_person_id", sa.Integer(), nullable=True),
        sa.Column("notify_channel", sa.Text(), nullable=False, server_default=""),
        sa.Column("excel_table_name", sa.Text(), nullable=True),
        sa.Column("shadow_mode", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(["owner_person_id"], ["org_people.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("path", "sheet_name", name="uq_managed_files_path_sheet"),
        sa.CheckConstraint("header_row >= 1", name="ck_managed_files_header_row"),
        sa.CheckConstraint(
            "first_data_row > header_row", name="ck_managed_files_first_data_row"
        ),
    )
    op.create_index("ix_managed_files_owner", "managed_files", ["owner_person_id"])

    op.create_table(
        "column_bindings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("field_id", sa.Integer(), nullable=False),
        sa.Column("column_letter", sa.Text(), nullable=False),
        sa.Column("header_text_exact", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending_review"),
        sa.Column("confidence", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("bound_by", sa.Text(), nullable=False),
        sa.Column("verified_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("verified_by", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
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
        sa.ForeignKeyConstraint(["file_id"], ["managed_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["field_id"], ["logical_fields.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "status IN ('active', 'auto_rebound', 'pending_review', 'retired')",
            name="ck_column_bindings_status",
        ),
        sa.CheckConstraint(
            "bound_by IN ('human', 'auto')", name="ck_column_bindings_bound_by"
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_column_bindings_confidence"
        ),
        sa.CheckConstraint(
            "column_letter ~ '^[A-Z]{1,3}$'", name="ck_column_bindings_column_letter"
        ),
        # A human-verified binding must record who verified it and when. This is
        # the gate every write depends on; an unattributed 'active' row would let
        # an agent promote its own guess into write eligibility.
        sa.CheckConstraint(
            "status <> 'active' OR (verified_by IS NOT NULL AND verified_at IS NOT NULL"
            " AND bound_by = 'human')",
            name="ck_column_bindings_active_is_verified",
        ),
    )
    # One live binding per (file, field). Retired rows are history and may repeat.
    op.create_index(
        "uq_column_bindings_live",
        "column_bindings",
        ["file_id", "field_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'retired'"),
    )
    op.create_index("ix_column_bindings_file", "column_bindings", ["file_id"])

    op.create_table(
        "column_fingerprints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("binding_id", sa.Integer(), nullable=False),
        sa.Column(
            "captured_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("header_normalized", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "header_aliases",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "dtype_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("distinct_ratio", sa.Float(), nullable=True),
        sa.Column("null_ratio", sa.Float(), nullable=True),
        sa.Column(
            "value_regex_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("minhash", postgresql.BYTEA(), nullable=True),
        sa.Column(
            "sample_values",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.ForeignKeyConstraint(["binding_id"], ["column_bindings.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_column_fingerprints_binding",
        "column_fingerprints",
        ["binding_id", "captured_at"],
    )

    op.create_table(
        "binding_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("binding_id", sa.Integer(), nullable=True),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("old_col", sa.Text(), nullable=True),
        sa.Column("new_col", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("runner_up_score", sa.Float(), nullable=True),
        sa.Column("shadow", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("actor", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["binding_id"], ["column_bindings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["file_id"], ["managed_files.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "event IN ('exact_match', 'auto_rebind', 'escalated', 'human_confirmed',"
            " 'write_blocked', 'proposed', 'shadow')",
            name="ck_binding_events_event",
        ),
    )
    op.create_index("ix_binding_events_file", "binding_events", ["file_id", "created_at"])
    op.create_index("ix_binding_events_binding", "binding_events", ["binding_id"])


def downgrade() -> None:
    op.drop_index("ix_binding_events_binding", table_name="binding_events")
    op.drop_index("ix_binding_events_file", table_name="binding_events")
    op.drop_table("binding_events")
    op.drop_index("ix_column_fingerprints_binding", table_name="column_fingerprints")
    op.drop_table("column_fingerprints")
    op.drop_index("ix_column_bindings_file", table_name="column_bindings")
    op.drop_index("uq_column_bindings_live", table_name="column_bindings")
    op.drop_table("column_bindings")
    op.drop_index("ix_managed_files_owner", table_name="managed_files")
    op.drop_table("managed_files")
    op.drop_table("logical_fields")
