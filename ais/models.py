from geoalchemy2.types import Geometry
from phladdress.parser import Parser
from ais import app_db as db
from ais.util import *

parser = Parser()

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

ADDRESS_FIELDS = [
    'address_low',
    'address_low_suffix',
    'address_low_frac',
    'address_high',
    'street_predir',
    'street_name',
    'street_suffix',
    'street_postdir',
    'unit_type',
    'unit_num',
    'street_full',
    'street_address',
]

class Address(db.Model):
    """A street address with parsed components."""
    id = db.Column(db.Integer, primary_key=True)
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

    def __init__(self, *args, **kwargs):
        if len(args) == 1:
            arg = args[0]
            # If a single string arg was passed, parse.
            if isinstance(arg, str):
                p = parser.parse(arg)
                if p['type'] != 'address':
                    raise ValueError('Not an address')
                c = p['components']
                kwargs = {
                    'address_low':          c['address']['low_num'],
                    'address_low_suffix':   c['address']['low_suffix'],
                    'address_low_frac':     c['address']['low_fractional'],
                    'address_high':         c['address']['high_num_full'],
                    'street_predir':        c['street']['predir'],
                    'street_name':          c['street']['name'],
                    'street_suffix':        c['street']['suffix'],
                    'street_postdir':       c['street']['postdir'],
                    'unit_type':            c['unit']['type'],
                    'unit_num':             c['unit']['num'],
                    'street_full':          c['street']['full'],
                    'street_address':       c['street_address'],
                }
        else:
            print(args)
        super(Address, self).__init__(**kwargs)

    def __str__(self):
        return 'Address: {}'.format(self.street_address)

    def __iter__(self):
        for key in ADDRESS_FIELDS:
            yield (key, getattr(self, key))

    @property
    def parity(self):
        low = self.address_low
        high = self.address_high
        if high:
            return parity_for_range(low, high)
        else:
            return parity_for_num(low)

    @property
    def base_address(self):
        return ' '.join([self.address_full, self.street_full])

    @property
    def base_address_no_suffix(self):
        return '{} {}'.format(self.address_full_num, self.street_full)

    @property
    def generic_unit(self):
        if self.unit_type is None:
            return self.street_address
        address_full = self.address_full
        street_full = self.street_full
        unit_type = '#'
        unit_num = self.unit_num
        return ' '.join([x for x in [address_full, street_full, unit_type, \
            unit_num] if x])

    @property
    def hundred_block(self):
        address_low = self.address_low
        return address_low - (address_low % 100)

    @property
    def unit_full(self):
        if self.unit_type:
            unit_full = self.unit_type
            if self.unit_num:
                unit_full = ' '.join([unit_full, self.unit_num])
            return unit_full
        return None
