"""Add current_salary and desired_salary columns to users and job_preferences tables

Revision ID: 20260119_1850
Revises: 20260116_0900
Create Date: 2026-01-19 18:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260119_1850'
down_revision: Union[str, None] = '20260116_0900'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add salary preference columns for form filling"""
    
    # Add columns to users table
    op.add_column(
        'users',
        sa.Column(
            'current_salary',
            sa.Integer(),
            nullable=True,
            comment='Current salary in USD (for form filling)'
        )
    )
    op.add_column(
        'users',
        sa.Column(
            'desired_salary',
            sa.Integer(),
            nullable=True,
            comment='Desired salary in USD (for form filling)'
        )
    )
    
    # Add columns to job_preferences table
    op.add_column(
        'job_preferences',
        sa.Column(
            'current_salary',
            sa.Integer(),
            nullable=True,
            comment='User\'s current salary (used for form filling)'
        )
    )
    op.add_column(
        'job_preferences',
        sa.Column(
            'desired_salary',
            sa.Integer(),
            nullable=True,
            comment='User\'s desired salary (used for form filling)'
        )
    )


def downgrade() -> None:
    """Remove salary preference columns"""
    
    # Remove from job_preferences table
    op.drop_column('job_preferences', 'desired_salary')
    op.drop_column('job_preferences', 'current_salary')
    
    # Remove from users table
    op.drop_column('users', 'desired_salary')
    op.drop_column('users', 'current_salary')
