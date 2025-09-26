"""merge_quality_score_and_uuid_changes

Revision ID: c384dca408e6
Revises: 58aaa9db54d5, 9a8b7c6d5e4f
Create Date: 2025-09-24 15:44:29.946640

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c384dca408e6'
down_revision = ('58aaa9db54d5', '9a8b7c6d5e4f')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass