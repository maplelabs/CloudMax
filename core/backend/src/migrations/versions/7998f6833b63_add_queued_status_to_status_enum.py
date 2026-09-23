"""add_queued_status_to_status_enum

Revision ID: 7998f6833b63
Revises: 277eacc00819
Create Date: 2025-11-06 06:07:35.572999

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7998f6833b63'
down_revision: Union[str, Sequence[str], None] = '277eacc00819'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'QUEUED' value to the status_enum type
    # PostgreSQL requires using ALTER TYPE ... ADD VALUE for enum types
    op.execute("ALTER TYPE status_enum ADD VALUE IF NOT EXISTS 'QUEUED' AFTER 'PENDING'")


def downgrade() -> None:
    # Note: PostgreSQL does not support removing enum values directly
    # To downgrade, you would need to:
    # 1. Create a new enum type without 'QUEUED'
    # 2. Alter all columns using the old enum to use the new enum
    # 3. Drop the old enum type
    # 4. Rename the new enum type to the old name
    # This is complex and risky, so we'll leave it as a no-op
    # If you need to remove 'QUEUED', you should manually handle the migration
    pass
