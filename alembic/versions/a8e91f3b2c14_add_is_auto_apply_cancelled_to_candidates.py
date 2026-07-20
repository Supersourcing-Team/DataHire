"""add is_auto_apply_cancelled to candidates

Revision ID: a8e91f3b2c14
Revises: 7772ec3ecea3
Create Date: 2026-07-20 15:12:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8e91f3b2c14'
down_revision: Union[str, Sequence[str], None] = '7772ec3ecea3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'candidates',
        sa.Column('is_auto_apply_cancelled', sa.Boolean(), server_default='false', nullable=False)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('candidates', 'is_auto_apply_cancelled')
