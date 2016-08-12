"""add trigram index on owner

Revision ID: 1056ffdb08f7
Revises: cfe84596b747
Create Date: 2016-06-27 16:36:38.070543

"""

# revision identifiers, used by Alembic.
revision = '1056ffdb08f7'
down_revision = 'cfe84596b747'

from alembic import op
import sqlalchemy as sa
import geoalchemy2


def upgrade():
    op.execute('''
        CREATE EXTENSION IF NOT EXISTS pg_trgm;
        CREATE INDEX address_summary_opa_owners_trigram_idx ON address_summary USING GIN (opa_owners gin_trgm_ops);
    ''')


def downgrade():
    op.execute('''
        DROP INDEX address_summary_opa_owners_trigram_idx;
        DROP EXTENSION pg_trgm;
    ''')
