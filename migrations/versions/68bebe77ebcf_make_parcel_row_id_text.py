"""Make parcel_row_id text

Revision ID: 68bebe77ebcf
Revises: b0a8ba013bf7
Create Date: 2016-03-28 12:25:17.427328

"""

# revision identifiers, used by Alembic.
revision = '68bebe77ebcf'
down_revision = 'b0a8ba013bf7'

from alembic import op
import sqlalchemy as sa
import geoalchemy2


def upgrade():
    op.alter_column('parcel_curb', 'parcel_row_id', type_=sa.Text())


def downgrade():
    op.alter_column('parcel_curb', 'parcel_row_id', type_=sa.Integer())
