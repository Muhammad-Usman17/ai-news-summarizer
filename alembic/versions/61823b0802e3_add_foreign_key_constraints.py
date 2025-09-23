"""Fix schema and foreign key constraints

Revision ID: 61823b0802e3
Revises: 
Create Date: 2025-09-23 15:55:17.212119

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '61823b0802e3'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fix news_analysis table to use string job_id and summary_ids
    # Change job_id from integer to varchar and update foreign key
    op.drop_constraint('news_analysis_job_id_fkey', 'news_analysis', type_='foreignkey')
    op.alter_column('news_analysis', 'job_id', type_=sa.String(), nullable=False)
    op.create_foreign_key(None, 'news_analysis', 'news_jobs', ['job_id'], ['job_id'])
    
    # Update summary_id to summary_ids (JSON array) if not already exists
    op.execute("ALTER TABLE news_analysis ADD COLUMN IF NOT EXISTS summary_ids JSON")
    op.execute("UPDATE news_analysis SET summary_ids = json_build_array(summary_id) WHERE summary_ids IS NULL AND summary_id IS NOT NULL")
    
    # Add missing columns to news_articles if not exists
    op.execute("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS published_at TIMESTAMP")
    op.execute("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS source VARCHAR")
    op.execute("ALTER TABLE news_articles ADD COLUMN IF NOT EXISTS scraped_at TIMESTAMP DEFAULT NOW()")
    
    # Add foreign key constraints
    op.create_foreign_key(None, 'news_articles', 'news_jobs', ['job_id'], ['job_id'])
    op.create_foreign_key(None, 'news_summaries', 'news_articles', ['article_id'], ['id'])
    op.create_foreign_key(None, 'news_summaries', 'news_jobs', ['job_id'], ['job_id'])


def downgrade() -> None:
    # Remove foreign key constraints
    op.drop_constraint(None, 'news_summaries', type_='foreignkey')
    op.drop_constraint(None, 'news_summaries', type_='foreignkey') 
    op.drop_constraint(None, 'news_articles', type_='foreignkey')
    op.drop_constraint(None, 'news_analysis', type_='foreignkey')
    
    # Revert news_analysis job_id back to integer
    op.alter_column('news_analysis', 'job_id', type_=sa.Integer(), nullable=False)
    op.create_foreign_key('news_analysis_job_id_fkey', 'news_analysis', 'news_jobs', ['job_id'], ['id'])
    
    # Remove added columns
    op.drop_column('news_articles', 'scraped_at')
    op.drop_column('news_articles', 'source') 
    op.drop_column('news_articles', 'published_at')