from geoalchemy2.types import Geometry
from ais import app_db as db


###########
# STREETS #
###########

class StreetSegment(db.Model):
    """A segment of a street centerline."""
    id = db.Column(db.Integer, primary_key=True)
    seg_id = db.Column(db.Integer)
    street_code = db.Column(db.Integer)
    street_predir = db.Column(db.Text)
    street_name = db.Column(db.Text)
    street_suffix = db.Column(db.Text)
    street_postdir = db.Column(db.Text)
    street_full = db.Column(db.Text)
    left_from = db.Column(db.Integer)
    left_to = db.Column(db.Integer)
    right_from = db.Column(db.Integer)
    right_to = db.Column(db.Integer)
    geom = db.Column(Geometry(geometry_type='LINESTRING', srid=4326))

    # aliases = db.relationship('StreetAlias', back_populates='street_segment')


class StreetAlias(db.Model):
    """Alternate name for a street segment."""
    id = db.Column(db.Integer, primary_key=True)
    street_predir = db.Column(db.Text)
    street_name = db.Column(db.Text)
    street_suffix = db.Column(db.Text)
    street_postdir = db.Column(db.Text)
    street_full = db.Column(db.Text)
    seg_id = db.Column(db.Integer)
    
    # street_segment = db.relationship('StreetSegment', back_populates='aliases')


###########
# PARCELS #
###########

class PwdParcel(db.Model):
    """A land parcel per PWD."""
    id = db.Column(db.Integer, primary_key=True)
    parcel_id = db.Column(db.Integer)
    street_address = db.Column(db.Text)
    address_low = db.Column(db.Integer)
    address_low_suffix = db.Column(db.Text)
    address_low_frac = db.Column(db.Text)
    address_high = db.Column(db.Integer)
    street_predir = db.Column(db.Text)
    street_name = db.Column(db.Text)
    street_suffix = db.Column(db.Text)
    street_postdir = db.Column(db.Text)
    unit_type = db.Column(db.Text)
    unit_num = db.Column(db.Text)
    street_full = db.Column(db.Text)
    geom = db.Column(Geometry(geometry_type='MULTIPOLYGON', srid=4326))


#############
# ADDRESSES #
#############

class Address(db.Model):
    """A street address with parsed components."""
    id = db.Column(db.Integer)
    street_address = db.Column(db.Text, primary_key=True)
    address_low = db.Column(db.Integer)
    address_low_suffix = db.Column(db.Text)
    address_low_frac = db.Column(db.Text)
    address_high = db.Column(db.Integer)
    street_predir = db.Column(db.Text)
    street_name = db.Column(db.Text)
    street_suffix = db.Column(db.Text)
    street_postdir = db.Column(db.Text)
    unit_type = db.Column(db.Text)
    unit_num = db.Column(db.Text)
    street_full = db.Column(db.Text)



# if __name__ == '__main__':

    # db.drop_all()
    # db.create_all()
