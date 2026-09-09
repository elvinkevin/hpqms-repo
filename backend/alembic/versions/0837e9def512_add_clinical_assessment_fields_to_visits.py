"""add_clinical_assessment_fields_to_visits

Revision ID: 0837e9def512
Revises: 04b035d279cf
Create Date: 2026-09-09 10:06:05.110923

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0837e9def512'
down_revision: Union[str, None] = '04b035d279cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # D3.2 Add clinical assessment columns
    op.add_column('visits', sa.Column('clinical_findings', sa.Text(), nullable=True))
    op.add_column('visits', sa.Column('diagnosis', sa.Text(), nullable=True))
    op.add_column('visits', sa.Column('treatment_plan', sa.Text(), nullable=True))


def downgrade() -> None:
    # Revert clinical assessment columns
    op.drop_column('visits', 'treatment_plan')
    op.drop_column('visits', 'diagnosis')
    op.drop_column('visits', 'clinical_findings')