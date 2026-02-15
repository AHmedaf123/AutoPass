"""Add Google OAuth columns to users table

Revision ID: 20260204_0100
Revises: 20260203_1300
Create Date: 2026-02-04 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260204_0100'
down_revision: Union[str, None] = '20260203_1300'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Google OAuth columns"""

    # Add columns to users table
    op.add_column(
        'users',
        sa.Column(
            'google_user_id',
            sa.String(255),
            nullable=True,
            comment='Google OAuth user ID'
        )
    )
    op.add_column(
        'users',
        sa.Column(
            'google_access_token',
            sa.Text,
            nullable=True,
            comment='Google OAuth access token'
        )
    )
    op.add_column(
        'users',
        sa.Column(
            'google_refresh_token',
            sa.Text,
            nullable=True,
            comment='Google OAuth refresh token'
        )
    )


def downgrade() -> None:
    """Remove Google OAuth columns"""

    # Remove columns from users table
    op.drop_column('users', 'google_user_id')
    op.drop_column('users', 'google_access_token')
    op.drop_column('users', 'google_refresh_token')