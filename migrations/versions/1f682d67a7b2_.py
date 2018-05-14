"""empty message

Revision ID: 1f682d67a7b2
Revises: 4c665272f1fc
Create Date: 2018-05-14 16:55:45.681733

"""

# revision identifiers, used by Alembic.
revision = '1f682d67a7b2'
down_revision = '4c665272f1fc'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_table('ng911',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('guid', sa.Text(), nullable=True),
    sa.Column('status', sa.Integer(), nullable=True),
    sa.Column('flag', sa.Text(), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('place_type', sa.Text(), nullable=True),
    sa.Column('placement', sa.Text(), nullable=True),
    sa.Column('street_address', sa.Text(), nullable=True),
    sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='POINT', srid=2272), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ng911_street_address'), 'ng911', ['street_address'], unique=False)
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_ng911_street_address'), table_name='ng911')
    op.drop_table('ng911')
    ### end Alembic commands ###
