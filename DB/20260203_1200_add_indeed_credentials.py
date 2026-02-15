"""Add indeed_username and indeed_password columns to users table

Revision ID: 20260203_1200
Revises: 20260119_1850
Create Date: 2026-02-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260203_1200'
down_revision: Union[str, None] = '20260119_1850'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Indeed credentials columns"""
    
    # Add columns to users table
    op.add_column(
        'users',
        sa.Column(
            'indeed_username',
            sa.String(255),
            nullable=True,
            comment='Indeed username/email for automated login'
        )
    )
    op.add_column(
        'users',
        sa.Column(
            'indeed_password',
            sa.String(255),
            nullable=True,
            comment='Indeed password for automated login'
        )
    )


def downgrade() -> None:
    """Remove Indeed credentials columns"""
    
    # Remove columns from users table
    op.drop_column('users', 'indeed_username')
    op.drop_column('users', 'indeed_password')