"""Add processing_time_sec and llm_metrics to triage and evaluation models

Revision ID: f3872377b49d
Revises: 862c380d6285
Create Date: 2025-10-21 12:13:31.086991

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'f3872377b49d'
down_revision: Union[str, Sequence[str], None] = '862c380d6285'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('evaluations', sa.Column('processing_time_sec', sa.Integer(), nullable=True))
    op.add_column('triages', sa.Column('processing_time_sec', sa.Integer(), nullable=True))
    op.add_column('evaluations', sa.Column('llm_metrics', JSONB, nullable=True))
    op.add_column('triages', sa.Column('llm_metrics', JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column('triages', 'llm_metrics')
    op.drop_column('evaluations', 'llm_metrics')
    op.drop_column('triages', 'processing_time_sec')
    op.drop_column('evaluations', 'processing_time_sec')
