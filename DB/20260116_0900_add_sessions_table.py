"""add sessions table for concurrent Selenium session tracking

Revision ID: 20260116_0900
Revises: f3a4b5c6d7e8
Create Date: 2026-01-16 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '20260116_0900'
down_revision: Union[str, None] = 'f3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create sessions table for tracking concurrent Selenium sessions per user.
    
    Features:
    - Multiple concurrent sessions per user (up to 3)
    - Session lifecycle tracking (active, idle, in_use, completed, failed)
    - Task tracking (current task_id, tasks_completed counter)
    - Error tracking and performance metrics
    - Automatic session expiration
    """
    op.create_table(
        'sessions',
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
            comment='Primary key - unique session record identifier'
        ),
        sa.Column(
            'session_id',
            sa.String(length=255),
            nullable=False,
            unique=True,
            comment='Unique session identifier for tracking across systems'
        ),
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment='Foreign key to users table'
        ),
        sa.Column(
            'status',
            sa.String(length=50),
            nullable=False,
            server_default='active',
            comment='Session status: active, idle, in_use, completed, failed, disposed'
        ),
        sa.Column(
            'session_start',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment='When session was created'
        ),
        sa.Column(
            'session_end',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='When session was completed or terminated'
        ),
        sa.Column(
            'last_activity',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment='Last time session was used'
        ),
        sa.Column(
            'task_id',
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment='Current task being processed by this session'
        ),
        sa.Column(
            'tasks_completed',
            sa.Integer(),
            nullable=False,
            server_default='0',
            comment='Counter of tasks completed in this session'
        ),
        sa.Column(
            'browser_type',
            sa.String(length=50),
            nullable=False,
            server_default='chrome',
            comment='Browser type (chrome, firefox, etc.)'
        ),
        sa.Column(
            'headless',
            sa.Integer(),
            nullable=False,
            server_default='1',
            comment='Whether browser runs headless (0=False, 1=True)'
        ),
        sa.Column(
            'session_duration_seconds',
            sa.Integer(),
            nullable=True,
            comment='Total session duration when completed'
        ),
        sa.Column(
            'login_time_seconds',
            sa.Integer(),
            nullable=True,
            comment='Time taken to login'
        ),
        sa.Column(
            'error_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
            comment='Count of errors encountered in session'
        ),
        sa.Column(
            'last_error_message',
            sa.Text(),
            nullable=True,
            comment='Most recent error message'
        ),
        sa.Column(
            'last_error_type',
            sa.String(length=100),
            nullable=True,
            comment='Type of most recent error'
        ),
        sa.Column(
            'metadata',
            sa.Text(),
            nullable=True,
            comment='JSON string for additional session metadata'
        ),
        sa.Column(
            'termination_reason',
            sa.String(length=255),
            nullable=True,
            comment='Why session ended (auto_disposal, timeout, user_logout, etc.)'
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment='Record creation timestamp'
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            comment='Record last update timestamp'
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id'),
        comment='Tracks concurrent Selenium sessions per user'
    )
    
    # Create indexes for efficient querying
    op.create_index('ix_sessions_session_id', 'sessions', ['session_id'], unique=True)
    op.create_index('ix_sessions_user_id', 'sessions', ['user_id'])
    op.create_index('ix_sessions_status', 'sessions', ['status'])
    op.create_index('ix_sessions_session_start', 'sessions', ['session_start'])
    op.create_index('ix_sessions_session_end', 'sessions', ['session_end'])
    op.create_index('ix_sessions_task_id', 'sessions', ['task_id'])
    
    # Composite index for finding active sessions by user
    op.create_index('ix_sessions_user_status', 'sessions', ['user_id', 'status'])
    
    # Index for last activity (for cleanup queries)
    op.create_index('ix_sessions_last_activity', 'sessions', ['last_activity'])


def downgrade() -> None:
    """Drop sessions table and all its indexes"""
    op.drop_index('ix_sessions_last_activity', table_name='sessions')
    op.drop_index('ix_sessions_user_status', table_name='sessions')
    op.drop_index('ix_sessions_task_id', table_name='sessions')
    op.drop_index('ix_sessions_session_end', table_name='sessions')
    op.drop_index('ix_sessions_session_start', table_name='sessions')
    op.drop_index('ix_sessions_status', table_name='sessions')
    op.drop_index('ix_sessions_user_id', table_name='sessions')
    op.drop_index('ix_sessions_session_id', table_name='sessions')
    op.drop_table('sessions')
