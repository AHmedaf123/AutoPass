"""Add exponential backoff support to apply_queue table

Migration: add_exponential_backoff
Date: 2024-01-20
Purpose: Add next_attempt_time column to support exponential backoff retry delays

Changes:
1. Add next_attempt_time column (DateTime with timezone, nullable) with index
2. Enables exponential backoff: 2s, 4s, 8s, 16s, 32s retry delays
3. Worker respects next_attempt_time when fetching pending tasks
"""

from alembic import op
import sqlalchemy as sa


def upgrade():
    """Add next_attempt_time column to apply_queue"""
    # Add next_attempt_time column for exponential backoff
    op.add_column(
        'apply_queue',
        sa.Column('next_attempt_time', sa.DateTime(timezone=True), nullable=True)
    )
    
    # Create index for performance (worker filters by this field)
    op.create_index(
        'ix_apply_queue_next_attempt_time',
        'apply_queue',
        ['next_attempt_time'],
        unique=False
    )


def downgrade():
    """Remove next_attempt_time column from apply_queue"""
    # Drop index
    op.drop_index('ix_apply_queue_next_attempt_time', table_name='apply_queue')
    
    # Drop column
    op.drop_column('apply_queue', 'next_attempt_time')
