"""add persistent_browser_profile

Revision ID: e02113ca2a48
Revises: ba415dcc8238
Create Date: 2026-01-01 00:50:11.876027

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e02113ca2a48'
down_revision: Union[str, None] = 'ba415dcc8238'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable columns for job_listings first
    op.add_column('job_listings', sa.Column('description_html', sa.Text(), nullable=True))
    op.add_column('job_listings', sa.Column('apply_link', sa.String(length=1000), nullable=True))
    op.add_column('job_listings', sa.Column('easy_apply', sa.Boolean(), nullable=True))
    op.add_column('job_listings', sa.Column('insights', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('job_listings', sa.Column('skills', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    
    # Set defaults for existing rows
    op.execute("UPDATE job_listings SET easy_apply = false WHERE easy_apply IS NULL")
    op.execute("UPDATE job_listings SET insights = '{}' WHERE insights IS NULL")
    op.execute("UPDATE job_listings SET skills = '[]' WHERE skills IS NULL")
    
    # Now make them NOT NULL
    op.alter_column('job_listings', 'easy_apply', existing_type=sa.Boolean(), nullable=False)
    op.alter_column('job_listings', 'insights', existing_type=postgresql.JSON(astext_type=sa.Text()), nullable=False)
    op.alter_column('job_listings', 'skills', existing_type=postgresql.JSON(astext_type=sa.Text()), nullable=False)
    
    # Add persistent_browser_profile to users (nullable)
    op.add_column('users', sa.Column('persistent_browser_profile', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'persistent_browser_profile')
    op.drop_column('job_listings', 'skills')
    op.drop_column('job_listings', 'insights')
    op.drop_column('job_listings', 'easy_apply')
    op.drop_column('job_listings', 'apply_link')
    op.drop_column('job_listings', 'description_html')
