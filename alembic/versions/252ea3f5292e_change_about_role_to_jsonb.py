"""change_about_role_to_jsonb

Revision ID: 252ea3f5292e
Revises: 8bc68107fb11
Create Date: 2026-07-31 16:08:23.086533

"""
from typing import Sequence, Union
import re

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '252ea3f5292e'
down_revision: Union[str, Sequence[str], None] = '8bc68107fb11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def convert_text_to_bullets(text: str) -> list:
    if not text:
        return []
    lines = text.split("\n")
    bullets = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Strip common bullet points and numbered list markers
        for bullet_char in ["-", "*", "•", "o ", "▪", "▫", "■", "□"]:
            if line.startswith(bullet_char):
                line = line[len(bullet_char):].strip()
                break
        else:
            match = re.match(r"^\d+\.\s+", line)
            if match:
                line = line[match.end():].strip()
        if line:
            bullets.append(line)
    return bullets or [text.strip()]


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('job_postings', sa.Column('about_role_jsonb', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    bind = op.get_bind()
    session = sa.orm.Session(bind=bind)
    
    # Define table schema dynamically
    job_postings_table = sa.Table(
        'job_postings',
        sa.MetaData(),
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('about_role', sa.Text),
        sa.Column('about_role_jsonb', postgresql.JSONB)
    )
    
    # Query and convert
    jobs = session.execute(sa.select(job_postings_table.c.id, job_postings_table.c.about_role)).all()
    for job_id, about_role_str in jobs:
        if about_role_str:
            bullets = convert_text_to_bullets(about_role_str)
            session.execute(
                job_postings_table.update()
                .where(job_postings_table.c.id == job_id)
                .values(about_role_jsonb=bullets)
            )
    session.commit()
    
    op.drop_column('job_postings', 'about_role')
    op.alter_column('job_postings', 'about_role_jsonb', new_column_name='about_role')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('job_postings', sa.Column('about_role_text', sa.Text(), nullable=True))
    
    bind = op.get_bind()
    session = sa.orm.Session(bind=bind)
    
    # Define table schema dynamically
    job_postings_table = sa.Table(
        'job_postings',
        sa.MetaData(),
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('about_role', postgresql.JSONB),
        sa.Column('about_role_text', sa.Text)
    )
    
    # Query and convert back to text
    jobs = session.execute(sa.select(job_postings_table.c.id, job_postings_table.c.about_role)).all()
    for job_id, about_role_json in jobs:
        if about_role_json:
            if isinstance(about_role_json, list):
                text_val = "\n".join(f"- {item}" for item in about_role_json)
            else:
                text_val = str(about_role_json)
            session.execute(
                job_postings_table.update()
                .where(job_postings_table.c.id == job_id)
                .values(about_role_text=text_val)
            )
    session.commit()
    
    op.drop_column('job_postings', 'about_role')
    op.alter_column('job_postings', 'about_role_text', new_column_name='about_role')
