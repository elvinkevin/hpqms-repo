"""Add a first-time administrator setup gate.

Revision ID: e7f8a9b0c1d2
Revises: d1f2a3b4c5d6
Create Date: 2026-09-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "d1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "staff",
        sa.Column(
            "admin_setup_complete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    # Accounts created by the old bootstrap/seed used these placeholder names.
    # Require those accounts to personalize their profile and replace the shared password.
    op.execute(
        "UPDATE staff SET admin_setup_complete = false "
        "WHERE role = 'ADMIN' AND first_name = 'Hospital' "
        "AND last_name = 'Administrator'"
    )


def downgrade() -> None:
    op.drop_column("staff", "admin_setup_complete")
