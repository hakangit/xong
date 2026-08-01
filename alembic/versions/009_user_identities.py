"""Identity rows keyed on (provider, subject); users.email as linking hint.

Fixes the split-account bug: OIDC and forward-auth keyed users on different
strings (preferred_username vs Remote-User), so one human got two rows.

Backfill choices:
- Every existing user gets a "proxy" identity for their username, so
  forward-auth and agent (acts_for) resolution keeps hitting the same rows.
- users.email is backfilled from org_people where a directory exists; on
  deployments without one this is a no-op. That email is what lets a later
  OIDC login link to the existing account (when XONG_LINK_DOMAINS allows).
- The unique index on lower(email) makes email-linking deterministic. If a
  deployment somehow has duplicate emails the index creation fails loudly —
  resolve the duplicates first rather than letting linking pick a row.

Revision ID: 009
Revises: 008
Create Date: 2026-08-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, Sequence[str], None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.Text(), nullable=True))
    op.create_table(
        "user_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("provider", "subject", name="uq_identity_provider_subject"),
    )
    op.execute(
        "INSERT INTO user_identities (provider, subject, user_id) "
        "SELECT 'proxy', username, id FROM users"
    )
    op.execute(
        "UPDATE users SET email = lower(op.email) "
        "FROM org_people op "
        "WHERE op.username = users.username AND op.email IS NOT NULL "
        "AND users.email IS NULL"
    )
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_table("user_identities")
    op.drop_column("users", "email")
