"""add session lifecycle fields

Revision ID: f3a4b5c6d7e8
Revises: e02113ca2a48
Create Date: 2026-01-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, None] = 'e02113ca2a48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add session lifecycle tracking to users table:
    - cooldown_until: Timestamp until which apply endpoint is blocked
    - last_session_outcome: Reason for session taint (e.g., 'shadow_throttle', 'missing_easy_apply')
    
    Critical for preventing 429 cascades by enforcing cooldown at API layer.
    """
    # Add cooldown_until column (nullable)
    op.add_column(
        'users',
        sa.Column(
            'cooldown_until',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Timestamp until which user is in cooldown after tainted session'
        )
    )
    
    # Add last_session_outcome column (nullable, indexed for monitoring)
    op.add_column(
        'users',
        sa.Column(
            'last_session_outcome',
            sa.String(length=50),
            nullable=True,
            comment='Reason for last session taint (e.g., shadow_throttle, missing_easy_apply)'
        )
    )
    
    # Create index on cooldown_until for efficient cooldown checks
    op.create_index(
        'ix_users_cooldown_until',
        'users',
        ['cooldown_until'],
        unique=False
    )
    
    # Create index on last_session_outcome for monitoring/analytics
    op.create_index(
        'ix_users_last_session_outcome',
        'users',
        ['last_session_outcome'],
        unique=False
    )


def downgrade() -> None:
    """Remove session lifecycle fields"""
    op.drop_index('ix_users_last_session_outcome', table_name='users')
    op.drop_index('ix_users_cooldown_until', table_name='users')
    op.drop_column('users', 'last_session_outcome')
    op.drop_column('users', 'cooldown_until')
