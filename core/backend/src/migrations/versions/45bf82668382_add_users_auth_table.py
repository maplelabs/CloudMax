"""add users auth table

Revision ID: 45bf82668382
Revises: 5fc4b1ca348f
Create Date: 2025-10-06 07:05:27.204714

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '45bf82668382'
down_revision: Union[str, Sequence[str], None] = 'a0de76065ee4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('username', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('email', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('hashed_password', sa.String(200), nullable=False),
        sa.Column('admin', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('users')
