"""adjust vitals storage and constraints

Revision ID: 1e5c9ca71e3b
Revises: a68266f830b5
Create Date: 2026-09-07 12:14:44.573178

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1e5c9ca71e3b'
down_revision: Union[str, None] = 'a68266f830b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Alter columns
    op.alter_column(
        'vitals', 'temperature',
        existing_type=sa.NUMERIC(precision=4, scale=1),
        type_=sa.String(length=20),
        existing_nullable=True
    )
    op.alter_column(
        'vitals', 'weight',
        existing_type=sa.NUMERIC(precision=5, scale=2),
        type_=sa.String(length=20),
        existing_nullable=True
    )

    # 2. Update foreign key constraints with explicit names
    op.drop_constraint('vitals_recorded_by_fkey', 'vitals', type_='foreignkey')
    op.drop_constraint('vitals_visit_id_fkey', 'vitals', type_='foreignkey')
    op.create_foreign_key('vitals_visit_id_fkey', 'vitals', 'visits', ['visit_id'], ['visit_id'])
    op.create_foreign_key('vitals_recorded_by_fkey', 'vitals', 'staff', ['recorded_by'], ['staff_id'])


def downgrade() -> None:
    # 1. Revert foreign keys
    op.drop_constraint('vitals_recorded_by_fkey', 'vitals', type_='foreignkey')
    op.drop_constraint('vitals_visit_id_fkey', 'vitals', type_='foreignkey')
    op.create_foreign_key('vitals_visit_id_fkey', 'vitals', 'visits', ['visit_id'], ['visit_id'], ondelete='CASCADE')
    op.create_foreign_key('vitals_recorded_by_fkey', 'vitals', 'staff', ['recorded_by'], ['staff_id'], ondelete='SET NULL')

    # 2. Revert column types
    op.alter_column(
        'vitals', 'weight',
        existing_type=sa.String(length=20),
        type_=sa.NUMERIC(precision=5, scale=2),
        existing_nullable=True
    )
    op.alter_column(
        'vitals', 'temperature',
        existing_type=sa.String(length=20),
        type_=sa.NUMERIC(precision=4, scale=1),
        existing_nullable=True
    )
