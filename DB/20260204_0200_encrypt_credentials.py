"""Replace plain text credentials with encrypted storage

Revision ID: 20260204_0200
Revises: 20260204_0100
Create Date: 2026-02-04 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260204_0200'
down_revision: Union[str, None] = '20260204_0100'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Replace plain text credentials with encrypted storage"""

    # Add encrypted columns
    op.add_column(
        'users',
        sa.Column(
            'encrypted_indeed_username',
            sa.Text,
            nullable=True,
            comment='Encrypted Indeed username'
        )
    )
    op.add_column(
        'users',
        sa.Column(
            'encrypted_indeed_password',
            sa.Text,
            nullable=True,
            comment='Encrypted Indeed password'
        )
    )
    op.add_column(
        'users',
        sa.Column(
            'encrypted_glassdoor_username',
            sa.Text,
            nullable=True,
            comment='Encrypted Glassdoor username'
        )
    )
    op.add_column(
        'users',
        sa.Column(
            'encrypted_glassdoor_password',
            sa.Text,
            nullable=True,
            comment='Encrypted Glassdoor password'
        )
    )


def downgrade() -> None:
    """Remove encrypted credential columns"""

    # Remove encrypted columns
    op.drop_column('users', 'encrypted_indeed_username')
    op.drop_column('users', 'encrypted_indeed_password')
    op.drop_column('users', 'encrypted_glassdoor_username')
    op.drop_column('users', 'encrypted_glassdoor_password')