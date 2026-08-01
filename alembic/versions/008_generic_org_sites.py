"""Allow deployment-defined organization site codes.

Revision ID: 008
Revises: 007
Create Date: 2026-08-01
"""

from typing import Sequence, Union

from alembic import op

revision: str = "008"
down_revision: Union[str, Sequence[str], None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_org_people_site", "org_people", type_="check")


def downgrade() -> None:
    op.create_check_constraint(
        "ck_org_people_site",
        "org_people",
        "site IS NULL OR site IN ('N', 'S', 'E', 'W')",
    )
