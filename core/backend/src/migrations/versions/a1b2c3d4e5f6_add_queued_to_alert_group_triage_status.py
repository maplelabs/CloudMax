"""add_queued_to_alert_group_triage_status

Revision ID: a1b2c3d4e5f6
Revises: 90d527efc5eb
Create Date: 2026-04-16 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '90d527efc5eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the existing check constraint
    op.drop_constraint('chk_alert_group_triage_status', 'alert_groups', type_='check')
    
    # Create new check constraint with 'queued' added
    op.create_check_constraint(
        'chk_alert_group_triage_status',
        'alert_groups',
        "triage_status IN ('pending', 'queued', 'in_progress', 'completed', 'failed')"
    )


def downgrade() -> None:
    # Drop the new constraint
    op.drop_constraint('chk_alert_group_triage_status', 'alert_groups', type_='check')
    
    # Restore old constraint without 'queued'
    op.create_check_constraint(
        'chk_alert_group_triage_status',
        'alert_groups',
        "triage_status IN ('pending', 'in_progress', 'completed', 'failed')"
    )
