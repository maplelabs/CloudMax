"""add_azure_anthropic_to_llm_provider_enum

Revision ID: 60c806a430f6
Revises: 7998f6833b63
Create Date: 2025-12-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '60c806a430f6'
down_revision: Union[str, Sequence[str], None] = '4569c8b1cbd0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add 'AZURE_ANTHROPIC' value to the llm_provider_enum type.

    This migration adds support for Azure Anthropic (Claude models hosted on Azure AI Foundry)
    as a new LLM provider option alongside the existing AZURE_OPENAI and AWS_BEDROCK_CLAUDE.

    Note: SQLAlchemy stores Python enum member names (not values) in PostgreSQL enums.
    The Python enum has: AZURE_ANTHROPIC = "azure-anthropic"
    PostgreSQL stores: 'AZURE_ANTHROPIC' (the member name, not the value)
    """
    # Add 'AZURE_ANTHROPIC' value to the llm_provider_enum type
    # PostgreSQL requires using ALTER TYPE ... ADD VALUE for enum types
    op.execute("ALTER TYPE llm_provider_enum ADD VALUE IF NOT EXISTS 'AZURE_ANTHROPIC'")


def downgrade() -> None:
    """
    Downgrade migration for removing AZURE_ANTHROPIC from llm_provider_enum.
    
    Note: PostgreSQL does not support removing enum values directly.
    To downgrade, you would need to:
    1. Update any rows using 'AZURE_ANTHROPIC' to a different provider
    2. Create a new enum type without 'AZURE_ANTHROPIC'
    3. Alter all columns using the old enum to use the new enum
    4. Drop the old enum type
    5. Rename the new enum type to the old name
    
    This is complex and risky, so we'll leave it as a no-op.
    If you need to remove 'AZURE_ANTHROPIC', you should manually handle the migration.
    """
    pass
