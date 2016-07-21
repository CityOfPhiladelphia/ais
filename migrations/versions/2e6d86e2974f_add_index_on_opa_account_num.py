"""add index on opa_account_num

Revision ID: 2e6d86e2974f
Revises: 1056ffdb08f7
Create Date: 2016-06-27 17:03:04.588774

"""

# revision identifiers, used by Alembic.
revision = '2e6d86e2974f'
down_revision = '1056ffdb08f7'

from alembic import op
import sqlalchemy as sa
import geoalchemy2


def upgrade():
    op.execute('''
      CREATE INDEX address_summary_opa_account_num_idx
        ON public.address_summary
        USING btree
        (opa_account_num);
    ''')


def downgrade():
    op.execute('''
      DROP INDEX address_summary_opa_account_num_idx;
    ''')
