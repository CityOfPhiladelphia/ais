"""add address sort index

Revision ID: cfe84596b747
Revises: a85916897681
Create Date: 2016-06-27 12:53:58.464729

"""

# revision identifiers, used by Alembic.
revision = 'cfe84596b747'
down_revision = 'a85916897681'

from alembic import op
import sqlalchemy as sa
import geoalchemy2


def upgrade():
    op.execute('''
        CREATE INDEX address_summary_sort_idx
          ON public.address_summary
          USING btree
          (street_name, street_suffix, street_predir, street_postdir, address_low, address_high, unit_num)
    ''')


def downgrade():
    op.execute('''
        DROP INDEX address_summary_sort_idx
    ''')
