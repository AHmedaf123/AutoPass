"""Add session_id and error_log columns to apply_queue table

Migration: add_task_logging_fields
Date: 2024-01-20
Purpose: Add comprehensive task logging fields for tracking session_id and structured error logs

Changes:
1. Add session_id column (String 255, nullable) with index for LinkedIn session tracking
2. Add error_log column (Text, nullable) for JSON array of error history
3. Enables structured logging of all task execution details
"""

from alembic import op
import sqlalchemy as sa


def upgrade():
    """Add session_id and error_log columns to apply_queue"""
    # Add session_id column for LinkedIn session tracking
    op.add_column(
        'apply_queue',
        sa.Column('session_id', sa.String(255), nullable=True)
    )
    
    # Add error_log column for structured error tracking (JSON array)
    op.add_column(
        'apply_queue',
        sa.Column('error_log', sa.Text(), nullable=True)
    )
    
    # Create index for session_id (used for filtering/reporting)
    op.create_index(
        'ix_apply_queue_session_id',
        'apply_queue',
        ['session_id'],
        unique=False
    )


def downgrade():
    """Remove session_id and error_log columns from apply_queue"""
    # Drop index
    op.drop_index('ix_apply_queue_session_id', table_name='apply_queue')
    
    # Drop columns
    op.drop_column('apply_queue', 'error_log')
    op.drop_column('apply_queue', 'session_id')
