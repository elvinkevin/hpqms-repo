"""rename vital_id to vitals_id

Revision ID: 04b035d279cf
Revises: 1e5c9ca71e3b
Create Date: 2026-09-07 18:13:16.095202

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '04b035d279cf'
down_revision: Union[str, None] = '1e5c9ca71e3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Rename column in-place to preserve primary key constraints & data
    op.alter_column('vitals', 'vital_id', new_column_name='vitals_id')

    # 2. Type cast temperature and weight columns safely to Float
    op.execute(
        "ALTER TABLE vitals ALTER COLUMN temperature TYPE DOUBLE PRECISION USING temperature::double precision;"
    )
    op.execute(
        "ALTER TABLE vitals ALTER COLUMN weight TYPE DOUBLE PRECISION USING weight::double precision;"
    )


def downgrade() -> None:
    # 1. Revert column name in-place
    op.alter_column('vitals', 'vitals_id', new_column_name='vital_id')

    # 2. Revert Float columns back to VARCHAR(20)
    op.alter_column(
        'vitals',
        'temperature',
        existing_type=sa.Float(),
        type_=sa.VARCHAR(length=20),
        existing_nullable=True,
    )
    op.alter_column(
        'vitals',
        'weight',
        existing_type=sa.Float(),
        type_=sa.VARCHAR(length=20),
        existing_nullable=True,
    )