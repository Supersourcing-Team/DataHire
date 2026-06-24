"""change requires_visa_sponsorship to integer

Revision ID: 1e4062a2f624
Revises: a51ab974cc6c
Create Date: 2026-06-24 14:38:28.877823

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1e4062a2f624'
down_revision: Union[str, Sequence[str], None] = 'a51ab974cc6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'job_postings', 
        'requires_visa_sponsorship',
        type_=sa.Integer(),
        existing_type=sa.Boolean(),
        postgresql_using="CASE WHEN requires_visa_sponsorship = true THEN 1 ELSE NULL END"
    )
    op.create_foreign_key(
        'fk_job_postings_requires_visa_sponsorship', 
        'job_postings', 
        'meta_visa_statuses', 
        ['requires_visa_sponsorship'], 
        ['id'], 
        ondelete='SET NULL'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'fk_job_postings_requires_visa_sponsorship', 
        'job_postings', 
        type_='foreignkey'
    )
    op.alter_column(
        'job_postings', 
        'requires_visa_sponsorship',
        type_=sa.Boolean(),
        existing_type=sa.Integer(),
        postgresql_using="CASE WHEN requires_visa_sponsorship IS NOT NULL THEN true ELSE false END"
    )
