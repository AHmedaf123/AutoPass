"""Add priority and job_id columns to apply_queue table

Migration: add_priority_to_apply_queue
Date: 2024-01-20
Purpose: Add task prioritization support to enable Easy Apply tasks to be processed before job discovery

Changes:
1. Add priority column (Integer, default 5) with index
2. Add job_id column (UUID, nullable) for linking to job_listings table
3. Update default priority values: HIGH=10 (job applications), NORMAL=5 (job discovery), LOW=1 (others)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


def upgrade():
    """Add priority and job_id columns to apply_queue"""
    # Add priority column with default value 5
    op.add_column(
        'apply_queue',
        sa.Column('priority', sa.Integer(), nullable=False, server_default='5')
    )
    
    # Add job_id column for job application tasks
    op.add_column(
        'apply_queue',
        sa.Column('job_id', UUID(as_uuid=True), nullable=True)
    )
    
    # Create indexes for performance
    op.create_index(
        'ix_apply_queue_priority',
        'apply_queue',
        ['priority'],
        unique=False
    )
    
    # Update existing job_application tasks to have HIGH priority (10)
    op.execute(
        """
        UPDATE apply_queue 
        SET priority = 10 
        WHERE task_type = 'job_application'
        """
    )
    
    # Update existing job_scraping tasks to have NORMAL priority (5) - already default
    # Update existing profile_update tasks to have LOW priority (1)
    op.execute(
        """
        UPDATE apply_queue 
        SET priority = 1 
        WHERE task_type = 'profile_update'
        """
    )


def downgrade():
    """Remove priority and job_id columns from apply_queue"""
    # Drop indexes
    op.drop_index('ix_apply_queue_priority', table_name='apply_queue')
    
    # Drop columns
    op.drop_column('apply_queue', 'job_id')
    op.drop_column('apply_queue', 'priority')
