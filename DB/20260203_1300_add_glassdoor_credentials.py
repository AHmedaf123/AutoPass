"""Add glassdoor_username and glassdoor_password columns to users table

Revision ID: 20260203_1300
Revises: 20260203_1200
Create Date: 2026-02-03 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260203_1300'
down_revision: Union[str, None] = '20260203_1200'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Glassdoor credentials columns"""
    
    # Add columns to users table
    op.add_column(
        'users',
        sa.Column(
            'glassdoor_username',
            sa.String(255),
            nullable=True,
            comment='Glassdoor username/email for automated login'
        )
    )
    op.add_column(
        'users',
        sa.Column(
            'glassdoor_password',
            sa.String(255),
            nullable=True,
            comment='Glassdoor password for automated login'
        )
    )


def downgrade() -> None:
    """Remove Glassdoor credentials columns"""
    
    # Remove columns from users table
    op.drop_column('users', 'glassdoor_username')
    op.drop_column('users', 'glassdoor_password')