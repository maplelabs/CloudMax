"""Add chaos_system_enabled configuration

Revision ID: a0de76065ee4
Revises: 10dfb93bc8bc
Create Date: 2025-10-01 16:21:41.935124

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a0de76065ee4'
down_revision: Union[str, Sequence[str], None] = '10dfb93bc8bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add chaos_system_enabled configuration to app_config
    op.add_column('app_config', sa.Column('chaos_system_enabled', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    # Remove chaos_system_enabled configuration from app_config
    op.drop_column('app_config', 'chaos_system_enabled')
