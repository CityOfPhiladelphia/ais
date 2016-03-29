"""Make State Plane again

Revision ID: dffe58fef261
Revises: 872041725db8
Create Date: 2016-03-24 11:21:22.990398

"""

# revision identifiers, used by Alembic.
revision = 'dffe58fef261'
down_revision = '872041725db8'

from alembic import op
import sqlalchemy as sa
import geoalchemy2


def upgrade():
    op.execute("ALTER TABLE pwd_parcel ALTER COLUMN geom TYPE geometry(MULTIPOLYGON,2272) USING ST_SetSrid(geom, 2272);")


def downgrade():
    op.execute("ALTER TABLE pwd_parcel ALTER COLUMN geom TYPE geometry(MULTIPOLYGON,4326) USING ST_SetSrid(geom, 4326);")
