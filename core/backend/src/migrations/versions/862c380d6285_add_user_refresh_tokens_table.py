"""add user_refresh_tokens table

Revision ID: 862c380d6285
Revises: 45bf82668382
Create Date: 2025-10-17 10:45:43.772108
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "862c380d6285"
down_revision: Union[str, Sequence[str], None] = "45bf82668382"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_refresh_tokens",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("token_hash", sa.String, unique=True, index=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("user_refresh_tokens")
