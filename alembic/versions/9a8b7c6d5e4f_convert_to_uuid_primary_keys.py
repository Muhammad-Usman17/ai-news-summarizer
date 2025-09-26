"""Convert to UUID primary keys

Revision ID: 9a8b7c6d5e4f
Revises: 61823b0802e3
Create Date: 2025-09-24 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '9a8b7c6d5e4f'
down_revision = '61823b0802e3'
branch_labels = None
depends_on = None


def upgrade():
    """Convert integer primary keys to UUIDs"""
    
    # Add UUID extension if it doesn't exist
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    
    # 1. First, add new UUID columns
    op.add_column('news_jobs', sa.Column('uuid', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False))
    op.add_column('news_articles', sa.Column('uuid', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False))
    op.add_column('news_summaries', sa.Column('uuid', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False))
    op.add_column('news_analysis', sa.Column('uuid', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False))
    
    # 2. Add new UUID foreign key columns
    op.add_column('news_articles', sa.Column('job_uuid', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('news_summaries', sa.Column('job_uuid', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('news_summaries', sa.Column('article_uuid', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('news_analysis', sa.Column('job_uuid', postgresql.UUID(as_uuid=True), nullable=True))
    
    # 3. Populate new UUID foreign keys by joining with existing job_id strings
    op.execute("""
        UPDATE news_articles 
        SET job_uuid = news_jobs.uuid 
        FROM news_jobs 
        WHERE news_articles.job_id = news_jobs.job_id
    """)
    
    op.execute("""
        UPDATE news_summaries 
        SET job_uuid = news_jobs.uuid 
        FROM news_jobs 
        WHERE news_summaries.job_id = news_jobs.job_id
    """)
    
    op.execute("""
        UPDATE news_summaries 
        SET article_uuid = news_articles.uuid 
        FROM news_articles 
        WHERE news_summaries.article_id = news_articles.id
    """)
    
    op.execute("""
        UPDATE news_analysis 
        SET job_uuid = news_jobs.uuid 
        FROM news_jobs 
        WHERE news_analysis.job_id = news_jobs.job_id
    """)
    
    # 4. Drop old foreign key constraints
    op.drop_constraint('news_articles_job_id_fkey', 'news_articles', type_='foreignkey')
    op.drop_constraint('news_summaries_job_id_fkey', 'news_summaries', type_='foreignkey')
    op.drop_constraint('news_summaries_article_id_fkey', 'news_summaries', type_='foreignkey')
    op.drop_constraint('news_analysis_job_id_fkey', 'news_analysis', type_='foreignkey')
    
    # 5. Drop old primary key constraints
    op.drop_constraint('news_jobs_pkey', 'news_jobs', type_='primary')
    op.drop_constraint('news_articles_pkey', 'news_articles', type_='primary')
    op.drop_constraint('news_summaries_pkey', 'news_summaries', type_='primary')
    op.drop_constraint('news_analysis_pkey', 'news_analysis', type_='primary')
    
    # 6. Drop old columns
    op.drop_column('news_jobs', 'id')
    op.drop_column('news_articles', 'id')
    op.drop_column('news_articles', 'job_id')
    op.drop_column('news_summaries', 'id')
    op.drop_column('news_summaries', 'job_id')
    op.drop_column('news_summaries', 'article_id')
    op.drop_column('news_analysis', 'id')
    op.drop_column('news_analysis', 'job_id')
    
    # 7. Rename new UUID columns to replace old ones
    op.alter_column('news_jobs', 'uuid', new_column_name='id')
    op.alter_column('news_articles', 'uuid', new_column_name='id')
    op.alter_column('news_articles', 'job_uuid', new_column_name='job_id')
    op.alter_column('news_summaries', 'uuid', new_column_name='id')
    op.alter_column('news_summaries', 'job_uuid', new_column_name='job_id')
    op.alter_column('news_summaries', 'article_uuid', new_column_name='article_id')
    op.alter_column('news_analysis', 'uuid', new_column_name='id')
    op.alter_column('news_analysis', 'job_uuid', new_column_name='job_id')
    
    # 8. Make foreign key columns NOT NULL
    op.alter_column('news_articles', 'job_id', nullable=False)
    op.alter_column('news_summaries', 'job_id', nullable=False)
    op.alter_column('news_summaries', 'article_id', nullable=False)
    op.alter_column('news_analysis', 'job_id', nullable=False)
    
    # 9. Create new primary key constraints
    op.create_primary_key('news_jobs_pkey', 'news_jobs', ['id'])
    op.create_primary_key('news_articles_pkey', 'news_articles', ['id'])
    op.create_primary_key('news_summaries_pkey', 'news_summaries', ['id'])
    op.create_primary_key('news_analysis_pkey', 'news_analysis', ['id'])
    
    # 10. Create new foreign key constraints
    op.create_foreign_key('news_articles_job_id_fkey', 'news_articles', 'news_jobs', ['job_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('news_summaries_job_id_fkey', 'news_summaries', 'news_jobs', ['job_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('news_summaries_article_id_fkey', 'news_summaries', 'news_articles', ['article_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('news_analysis_job_id_fkey', 'news_analysis', 'news_jobs', ['job_id'], ['id'], ondelete='CASCADE')
    
    # 11. Create indexes on new UUID columns
    op.create_index('ix_news_jobs_id', 'news_jobs', ['id'])
    op.create_index('ix_news_articles_id', 'news_articles', ['id'])
    op.create_index('ix_news_articles_job_id', 'news_articles', ['job_id'])
    op.create_index('ix_news_summaries_id', 'news_summaries', ['id'])
    op.create_index('ix_news_summaries_job_id', 'news_summaries', ['job_id'])
    op.create_index('ix_news_analysis_id', 'news_analysis', ['id'])
    op.create_index('ix_news_analysis_job_id', 'news_analysis', ['job_id'])
    
    # 12. Also add a job_type column and workflow_run_id for better tracking
    op.add_column('news_jobs', sa.Column('job_type', sa.String(50), nullable=False, server_default='manual'))
    op.add_column('news_jobs', sa.Column('workflow_run_id', sa.String, nullable=True))
    op.add_column('news_jobs', sa.Column('processed_date', sa.Date, nullable=True))  # Date for which news was processed
    
    # Add index on processed_date for efficient historical queries
    op.create_index('ix_news_jobs_processed_date', 'news_jobs', ['processed_date'])
    op.create_index('ix_news_jobs_job_type', 'news_jobs', ['job_type'])


def downgrade():
    """Revert back to integer primary keys (complex rollback)"""
    
    # This is a complex rollback, typically not recommended in production
    # For now, just raise an exception to prevent accidental rollback
    raise Exception("Downgrading from UUID to integer PKs is not supported. Create a new database if needed.")