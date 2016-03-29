"""Make State Plane

Revision ID: 872041725db8
Revises: 685d969dbc0e
Create Date: 2016-03-23 15:46:13.297247

"""

# revision identifiers, used by Alembic.
revision = '872041725db8'
down_revision = '685d969dbc0e'

from alembic import op
import sqlalchemy as sa
import geoalchemy2


def upgrade():
    op.execute("ALTER TABLE street_segment ALTER COLUMN geom TYPE geometry(LINESTRING,2272) USING ST_SetSrid(geom, 2272);")


def downgrade():
    op.execute("ALTER TABLE street_segment ALTER COLUMN geom TYPE geometry(LINESTRING,4326) USING ST_SetSrid(geom, 4326);")
