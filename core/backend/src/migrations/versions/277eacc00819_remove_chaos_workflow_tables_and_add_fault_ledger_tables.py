"""Remove chaos_workflow tables and add fault_ledger tables

Revision ID: 277eacc00819
Revises: ad359fb9d063
Create Date: 2025-10-31 07:35:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql import func

# revision identifiers, used by Alembic.
revision: str = '277eacc00819'
down_revision: Union[str, Sequence[str], None] = 'ad359fb9d063'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop chaos_workflow_run_to_alerts table first (due to foreign key constraints)
    # Use if_exists=True to handle cases where tables may not exist
    op.drop_table('chaos_workflow_run_to_alerts', if_exists=True)

    # Drop chaos_workflow_runs table
    op.drop_table('chaos_workflow_runs', if_exists=True)

    op.create_table(
        'fault_ledger',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('fault_name', sa.String(), nullable=False),
        sa.Column('fault_description', sa.String(), nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('configured_duration', sa.Float(), nullable=False),
        sa.Column('target_system', sa.String(), nullable=False),
        sa.Column('severity', sa.String(), nullable=False),
        sa.Column('trigger_mechanism', sa.String(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False, unique=True),
        sa.Column('alert_names', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
    )

    # Create fault_ledger_to_alerts mapping table
    op.create_table(
        'fault_ledger_to_alerts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('fault_ledger_id', sa.Integer(), nullable=False),
        sa.Column('alert_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'),
                  nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'),
                  nullable=False),
        sa.ForeignKeyConstraint(['alert_id'], ['alerts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['fault_ledger_id'], ['fault_ledger.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('alert_id', name='uq_alert_single_fault_ledger')
    )

    # Convert status values to lowercase
    op.execute("UPDATE fault_ledger SET status = LOWER(status)")


def downgrade() -> None:
    # Drop mapping table first (due to foreign key constraints)
    op.drop_table('fault_ledger_to_alerts')

    # Drop fault_ledger table
    op.drop_table('fault_ledger')
