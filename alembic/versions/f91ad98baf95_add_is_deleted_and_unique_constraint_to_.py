"""add_is_deleted_and_unique_constraint_to_resumes

Revision ID: f91ad98baf95
Revises: 516702c4c244
Create Date: 2026-07-14 18:01:23.259580

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f91ad98baf95'
down_revision: Union[str, Sequence[str], None] = '516702c4c244'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('resumes', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    
    # Data cleaning: Keep only the latest primary resume for each candidate as primary
    op.execute(
        """
        WITH ranked_resumes AS (
            SELECT id, candidate_id,
                   ROW_NUMBER() OVER(PARTITION BY candidate_id ORDER BY created_at DESC, id DESC) as rn
            FROM resumes
            WHERE is_primary = true
        )
        UPDATE resumes
        SET is_primary = false
        WHERE id IN (
            SELECT id FROM ranked_resumes WHERE rn > 1
        );
        """
    )
    
    op.create_index('uq_candidate_primary_resume', 'resumes', ['candidate_id'], unique=True, postgresql_where=sa.text('is_primary = true'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_candidate_primary_resume', table_name='resumes')
    op.drop_column('resumes', 'is_deleted')
