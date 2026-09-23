"""align audit_log columns with model and service usage

Renames audit_logs.staff_id -> performed_by (now nullable, since some
system-triggered events have no acting staff member) and
audit_logs.entity -> entity_type, matching the AuditService and the
AuditLogRead schema. Adds indexes used by the admin audit queries.

Revision ID: d1f2a3b4c5d6
Revises: a77591638e93
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1f2a3b4c5d6'
down_revision: Union[str, None] = 'a77591638e93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'audit_logs',
        'staff_id',
        new_column_name='performed_by',
        nullable=True,
    )
    op.alter_column(
        'audit_logs',
        'entity',
        new_column_name='entity_type',
    )
    op.create_index('idx_audit_entity', 'audit_logs', ['entity_type', 'entity_id'])
    op.create_index('idx_audit_performed_by', 'audit_logs', ['performed_by'])
    op.create_index('idx_audit_action', 'audit_logs', ['action'])


def downgrade() -> None:
    op.drop_index('idx_audit_action', table_name='audit_logs')
    op.drop_index('idx_audit_performed_by', table_name='audit_logs')
    op.drop_index('idx_audit_entity', table_name='audit_logs')
    op.alter_column(
        'audit_logs',
        'entity_type',
        new_column_name='entity',
    )
    # staff_id was NOT NULL originally; any rows written with a NULL
    # performed_by must be removed before the constraint can be restored.
    op.execute("DELETE FROM audit_logs WHERE performed_by IS NULL")
    op.alter_column(
        'audit_logs',
        'performed_by',
        new_column_name='staff_id',
        nullable=False,
    )
