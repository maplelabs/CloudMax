"""Add complete alert grouping and correlation schema

Revision ID: 90d527efc5eb
Revises: 60c806a430f6
Create Date: 2026-03-31 15:30:00.000000

This migration consolidates all alert grouping changes into a single file:
1. Creates alert_groups table with all required fields
2. Adds group_id to alerts table
3. Adds alert_grouping_config JSONB to app_config
4. Adds alert_grouping_enabled flag to app_config
5. Extends evaluations table to support group evaluations
6. Adds retry_count to alert_groups
7. Creates triggers for auto-cleanup of empty groups
"""
from typing import Sequence, Union
import json
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '90d527efc5eb'
down_revision: Union[str, Sequence[str], None] = '60c806a430f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply all alert grouping schema changes in correct order."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    table_names = inspector.get_table_names()

    # ================================================================
    # PART 1: Clean up any legacy alert grouping artifacts
    # ================================================================
    if "alerts" in table_names:
        # Drop old foreign key constraint if present
        fk_constraints = inspector.get_foreign_keys("alerts")
        if any(c.get("name") == "fk_alerts_group_id" for c in fk_constraints):
            op.drop_constraint("fk_alerts_group_id", "alerts", type_="foreignkey")
        
        # Drop legacy indexes if they exist (using raw SQL with IF EXISTS)
        op.execute("DROP INDEX IF EXISTS ix_alerts_group_id")
        op.execute("DROP INDEX IF EXISTS ix_alerts_embedding_hnsw")
        
        # Drop legacy columns if present
        existing_columns = {col["name"] for col in inspector.get_columns("alerts")}
        if "group_id" in existing_columns:
            op.drop_column("alerts", "group_id")
        if "embedding" in existing_columns:
            op.drop_column("alerts", "embedding")

    # Drop any legacy alert_groups table if it exists
    if "alert_groups" in table_names:
        op.drop_table("alert_groups")

    # ================================================================
    # PART 2: Create alert_groups table
    # ================================================================
    severity_enum = postgresql.ENUM('P1', 'P2', 'P3', name='severity_enum', create_type=False)
    
    op.create_table('alert_groups',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('group_name', sa.String(length=500), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='active', nullable=False),
        sa.Column('severity', severity_enum, server_default='P3', nullable=False),
        
        # Triage information (populated by triage worker)
        sa.Column('root_cause_summary', sa.Text(), nullable=True),
        sa.Column('triage_status', sa.String(length=50), server_default='pending', nullable=False),
        sa.Column('triaged_at', sa.TIMESTAMP(timezone=True), nullable=True),
        
        # LangGraph thread ID and RQ job ID (for journey tracking)
        sa.Column('thread_id', sa.String(length=255), nullable=True),
        sa.Column('job_id', sa.String(length=255), nullable=True),
        
        # Error handling
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        
        # Performance metrics
        sa.Column('tokens_used', sa.Integer(), nullable=True),
        sa.Column('price_usd', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('processing_time_sec', sa.Integer(), nullable=True),
        sa.Column('llm_metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        
        # Grouping decision metadata
        sa.Column('grouping_confidence', sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column('grouping_reasoning', sa.Text(), nullable=True),
        
        # Audit fields
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("status IN ('active', 'resolved')", name='chk_alert_group_status'),
        sa.CheckConstraint("triage_status IN ('pending', 'in_progress', 'completed', 'failed')", name='chk_alert_group_triage_status'),
        sa.CheckConstraint("grouping_confidence >= 0.00 AND grouping_confidence <= 1.00", name='chk_alert_group_confidence'),
    )

    # Create indexes for alert_groups
    op.create_index('idx_alert_groups_active_lookup', 'alert_groups', ['updated_at'], unique=False,
                    postgresql_where=sa.text("status = 'active'"))
    op.create_index('idx_alert_groups_thread_id', 'alert_groups', ['thread_id'], unique=False)
    op.create_index('idx_alert_groups_job_id', 'alert_groups', ['job_id'], unique=False)
    op.create_index('idx_alert_groups_created_at', 'alert_groups', ['created_at'], unique=False)
    op.create_index('idx_alert_groups_triage_status', 'alert_groups', ['triage_status'], unique=False)
    op.create_index('idx_alert_groups_triage_created', 'alert_groups',
                    ['triage_status', 'created_at'], unique=False)

    # ================================================================
    # PART 3: Add group_id column to alerts table
    # ================================================================
    op.add_column('alerts', sa.Column('group_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_alerts_group_id', 'alerts', 'alert_groups',
                          ['group_id'], ['id'], ondelete='SET NULL')
    op.create_index('idx_alerts_group_id', 'alerts', ['group_id'], unique=False,
                    postgresql_where=sa.text("group_id IS NOT NULL"))
    op.create_index('idx_alerts_ungrouped', 'alerts', ['created_at'], unique=False,
                    postgresql_where=sa.text("group_id IS NULL"))

    # ================================================================
    # PART 4: Create trigger to automatically delete empty groups
    # ================================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION delete_empty_groups()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Delete the group if no alerts remain
            DELETE FROM alert_groups
            WHERE id = OLD.group_id
            AND NOT EXISTS (
                SELECT 1 FROM alerts WHERE group_id = OLD.group_id
            );
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trigger_delete_empty_groups
            AFTER DELETE ON alerts
            FOR EACH ROW
            WHEN (OLD.group_id IS NOT NULL)
            EXECUTE FUNCTION delete_empty_groups();
    """)

    # ================================================================
    # PART 5: Add alert_grouping_config to app_config
    # ================================================================
    op.add_column('app_config',
                  sa.Column('alert_grouping_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # Set default configuration for existing rows using parameterized query
    default_config = {
        "batch_grouping_interval_sec": 300,
        "ungrouped_retry_interval_sec": 300,
        "group_triage_interval_sec": 300,
        "ungrouped_alerts_lookback_hours": 24,
        "active_groups_lookback_minutes": 30,
        "new_group_validation_lookback_minutes": 30,
        "standalone_alert_timeout_minutes": 30,
        "max_alerts_per_batch": 20,
        "max_active_groups_context": 20,
        "max_ungrouped_for_validation": 50
    }

    config_json = json.dumps(default_config)
    # Use direct string formatting - bindparams doesn't work with ::jsonb cast
    op.execute(
        f"UPDATE app_config SET alert_grouping_config = '{config_json}'::jsonb WHERE alert_grouping_config IS NULL"
    )

    # ================================================================
    # PART 6: Add alert_grouping_enabled flag to app_config
    # ================================================================
    op.add_column('app_config', sa.Column('alert_grouping_enabled',
                                          sa.Boolean(), server_default='true', nullable=False))

    # ================================================================
    # PART 7: Extend evaluations table for group evaluations
    # ================================================================
    # Make alert_id nullable
    op.alter_column('evaluations', 'alert_id',
                    existing_type=sa.Integer(),
                    nullable=True)

    # Clean up orphaned evaluations (where alert_id is NULL)
    # These are invalid rows that would violate the constraint
    # Using parameterized query for safety
    op.execute(
        sa.text("DELETE FROM evaluations WHERE alert_id IS NULL")
    )

    # Add group_id column
    op.add_column('evaluations',
                  sa.Column('group_id', sa.Integer(), nullable=True))

    # Add foreign key constraint
    op.create_foreign_key('evaluations_group_id_fkey',
                          'evaluations', 'alert_groups',
                          ['group_id'], ['id'],
                          ondelete='CASCADE')

    # Add index on group_id
    op.create_index('ix_evaluations_group_id', 'evaluations', ['group_id'])

    # Add check constraint to ensure exactly one of alert_id or group_id is set
    op.create_check_constraint(
        'check_alert_or_group',
        'evaluations',
        '(alert_id IS NOT NULL AND group_id IS NULL) OR (alert_id IS NULL AND group_id IS NOT NULL)'
    )


def downgrade() -> None:
    """Remove all alert grouping schema changes."""

    # Remove evaluations group support
    op.drop_constraint('check_alert_or_group', 'evaluations', type_='check')
    op.drop_index('ix_evaluations_group_id', 'evaluations')
    op.drop_constraint('evaluations_group_id_fkey', 'evaluations', type_='foreignkey')
    op.drop_column('evaluations', 'group_id')
    op.alter_column('evaluations', 'alert_id',
                    existing_type=sa.Integer(),
                    nullable=False)

    # Remove app_config columns
    op.drop_column('app_config', 'alert_grouping_enabled')
    op.drop_column('app_config', 'alert_grouping_config')

    # Drop the trigger and function
    op.execute("DROP TRIGGER IF EXISTS trigger_delete_empty_groups ON alerts;")
    op.execute("DROP FUNCTION IF EXISTS delete_empty_groups();")

    # Drop indexes on alerts
    op.drop_index('idx_alerts_ungrouped', table_name='alerts')
    op.drop_index('idx_alerts_group_id', table_name='alerts')
    op.drop_constraint('fk_alerts_group_id', 'alerts', type_='foreignkey')
    op.drop_column('alerts', 'group_id')

    # Drop indexes on alert_groups
    op.drop_index('idx_alert_groups_triage_created', table_name='alert_groups')
    op.drop_index('idx_alert_groups_triage_status', table_name='alert_groups')
    op.drop_index('idx_alert_groups_created_at', table_name='alert_groups')
    op.drop_index('idx_alert_groups_job_id', table_name='alert_groups')
    op.drop_index('idx_alert_groups_thread_id', table_name='alert_groups')
    op.drop_index('idx_alert_groups_active_lookup', table_name='alert_groups')

    # Drop alert_groups table
    op.drop_table('alert_groups')

