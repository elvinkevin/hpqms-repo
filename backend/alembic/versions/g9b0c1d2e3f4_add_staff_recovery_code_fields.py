"""Add hashed, expiring one-time staff recovery codes.

Revision ID: g9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-09-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g9b0c1d2e3f4"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "staff",
        sa.Column("password_reset_code_hash", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "staff",
        sa.Column("password_reset_code_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("staff", "password_reset_code_expires_at")
    op.drop_column("staff", "password_reset_code_hash")
