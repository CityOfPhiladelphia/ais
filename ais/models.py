import copy
from geoalchemy2.types import Geometry
from phladdress.parser import Parser
from ais import app, app_db as db
from ais.util import *

parser = Parser()
config = app.config
ENGINE_SRID = config['ENGINE_SRID']

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
    geom = db.Column(Geometry(geometry_type='LINESTRING', srid=ENGINE_SRID))

    # aliases = db.relationship('StreetAlias', back_populates='street_segment')

    def __str__(self):
        attrs = {
            'low':      min(self.left_from, self.right_from),
            # 'high':     max(self.left_to, self.right_to),
            'street':   self.street_full,
        }
        return 'StreetSegment: {low} {street}'.format(**attrs)

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
    geom = db.Column(Geometry(geometry_type='MULTIPOLYGON', srid=ENGINE_SRID))

class DorParcel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    parcel_id = db.Column(db.Text)
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
    source_object_id = db.Column(db.Integer)
    source_address = db.Column(db.Text)
    geom = db.Column(Geometry(geometry_type='MULTIPOLYGON', srid=ENGINE_SRID))


##############
# PROPERTIES #
##############

class OpaProperty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_num = db.Column(db.Text)
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
    source_address = db.Column(db.Text)
    tencode = db.Column(db.Text)
    owners = db.Column(db.Text)


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
    def address_full(self):
        """Returns full primary address (e.g. 1003R-07 1/2)"""
        address_full = str(self.address_low)
        if self.address_low_suffix:
            address_full += self.address_low_suffix
        if self.address_low_frac:
            address_full += ' ' + self.address_low_frac
        if self.address_high:
            address_full += '-' + str(self.address_high)[-2:]
        return address_full

    @property
    def address_full_num(self):
        '''
        Returns all numeric components of address. Example:
        1234A-36 1/2 => 1234-36
        '''
        num = str(self.address_low)
        if self.address_high:
            address_high = str(self.address_high)
            if len(address_high) < 2:
                # address_high = '0' + address_high
                num += '-' + str(address_high)
            else:
                num += '-' + str(address_high)[-2:]
        return num

    @property
    def base_address(self):
        return ' '.join([self.address_full, self.street_full])

    @property
    def base_address_no_suffix(self):
        return '{} {}'.format(self.address_full_num, self.street_full)

    @property
    def is_base(self):
        if self.unit_type or self.address_low_suffix:
            return False
        return True

    @property
    def child_addresses(self):
        """Returns a list of individual street addresses for a range"""
        child_addresses = []
        for child_num in self.child_nums:
            child_obj = copy.copy(self)
            child_obj.address_high = None
            child_obj.address_low = child_num
            child_addresses.append(child_obj)
        return child_addresses

    @property
    def child_nums(self):
        """Returns a list of individual address nums for a range"""
        if self.address_high is None or self.unit_type is not None:
            return []
        child_num_list = []
        for x in range(self.address_low, self.address_high + 1, 2):
            child_num_list.append(x)
        return child_num_list

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

class AddressTag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    street_address = db.Column(db.Text)
    key = db.Column(db.Text)
    value = db.Column(db.Text)

class SourceAddress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source_name = db.Column(db.Text)
    source_address = db.Column(db.Text)
    street_address = db.Column(db.Text)

class AddressLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    address_1 = db.Column(db.Text)
    relationship = db.Column(db.Text)
    address_2 = db.Column(db.Text)


#######################
# RELATIONSHIP TABLES #
#######################

class AddressStreet(db.Model):
    '''
    Stores information about the relationship between addresses and street segs
    '''
    id = db.Column(db.Integer, primary_key=True)
    street_address = db.Column(db.Text)
    seg_id = db.Column(db.Integer)
    seg_side = db.Column(db.Text)

class AddressParcel(db.Model):
    '''
    Stores information about the relationship between addresses and PWD parcels.
    '''
    id = db.Column(db.Integer, primary_key=True)
    street_address = db.Column(db.Text)
    parcel_source = db.Column(db.Text)
    # Use AIS primary key because parcels don't have unique ID
    parcel_row_id = db.Column(db.Integer)
    # possible values: base, base_no_suffix, generic_unit,
    # parcel_in_address_range, address_in_parcel_range
    match_type = db.Column(db.Text)

class AddressProperty(db.Model):
    '''
    Stores information about the relationship between addresses and OPA
    properties.
    '''
    id = db.Column(db.Integer, primary_key=True)
    street_address = db.Column(db.Text)
    opa_account_num = db.Column(db.Text)
    match_type = db.Column(db.Text)

class AddressZip(db.Model):
    '''
    Stores information about the relationship between addresses and ZIP ranges.
    '''
    id = db.Column(db.Integer, primary_key=True)
    street_address = db.Column(db.Text)
    usps_id = db.Column(db.Text)
    match_type = db.Column(db.Text)


#############
# GEOCODING #
#############

class Geocode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    street_address = db.Column(db.Text)
    geocode_type = db.Column(db.Text)     # parcel, curb, street
    geom = db.Column(Geometry(geometry_type='POINT', srid=ENGINE_SRID))

class Curb(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    curb_id = db.Column(db.Integer)
    geom = db.Column(Geometry(geometry_type='MULTIPOLYGON', srid=ENGINE_SRID))

class ParcelCurb(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    parcel_source = db.Column(db.Text)
    # Use AIS primary key because parcels don't have unique ID
    parcel_row_id = db.Column(db.Text)
    curb_id = db.Column(db.Integer)


#################
# SERVICE AREAS #
#################

class ServiceAreaLayer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    layer_id = db.Column(db.Text)
    name = db.Column(db.Text)
    description = db.Column(db.Text)

class ServiceAreaPolygon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    layer_id = db.Column(db.Text)
    source_object_id = db.Column(db.Integer)  # The object ID in the source dataset
    value = db.Column(db.Text)
    geom = db.Column(Geometry(geometry_type='MULTIPOLYGON', srid=ENGINE_SRID))

class ServiceAreaLineSingle(db.Model):
    '''
    A service area boundary line with a single value for right and left sides.
    '''
    id = db.Column(db.Integer, primary_key=True)
    layer_id = db.Column(db.Text)
    source_object_id = db.Column(db.Integer)  # The object ID in the source dataset
    seg_id = db.Column(db.Integer)
    value = db.Column(db.Text)

class ServiceAreaLineDual(db.Model):
    '''
    A service area boundary line with a separate values for right and left
    sides.
    '''
    id = db.Column(db.Integer, primary_key=True)
    layer_id = db.Column(db.Text)
    source_object_id = db.Column(db.Integer)  # The object ID in the source dataset
    seg_id = db.Column(db.Integer)
    left_value = db.Column(db.Text)
    right_value = db.Column(db.Text)

class ServiceAreaDiff(db.Model):
    '''
    Layer of all Address Summary points where a difference was observed between 
    AIS and ULRS. One point per difference.
    '''
    id = db.Column(db.Integer, primary_key=True)
    street_address = db.Column(db.Text)
    layer_id = db.Column(db.Text)
    ais_value = db.Column(db.Text)
    ulrs_value = db.Column(db.Text)
    distance = db.Column(db.Float)
    geom = db.Column(Geometry(geometry_type='POINT', srid=ENGINE_SRID))

#############
# ZIP CODES #
#############

class ZipRange(db.Model):
    '''
    This is essentially a direct copy of the USPS ZIP+4 table.
    '''
    id = db.Column(db.Integer, primary_key=True)
    usps_id = db.Column(db.Text)
    address_low = db.Column(db.Integer)
    address_high = db.Column(db.Integer)
    address_oeb = db.Column(db.Text)
    street_predir = db.Column(db.Text)
    street_name = db.Column(db.Text)
    street_suffix = db.Column(db.Text)
    street_postdir = db.Column(db.Text)
    unit_type = db.Column(db.Text)
    unit_low = db.Column(db.Text)
    unit_high = db.Column(db.Text)
    unit_oeb = db.Column(db.Text)
    zip_code = db.Column(db.Text)
    zip_4 = db.Column(db.Text)


############
# PRODUCTS #
############

class AddressSummary(db.Model):
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
    zip_code = db.Column(db.Text)
    zip_4 = db.Column(db.Text)

    # Foreign keys
    seg_id = db.Column(db.Integer)
    seg_side = db.Column(db.Text)
    pwd_parcel_id = db.Column(db.Text)
    dor_parcel_id = db.Column(db.Text)
    opa_account_num = db.Column(db.Text)
    opa_owners = db.Column(db.Text)
    opa_address = db.Column(db.Text)
    info_residents = db.Column(db.Text)
    info_companies = db.Column(db.Text)
    pwd_account_nums = db.Column(db.Text)
    li_address_key = db.Column(db.Text)
    voters = db.Column(db.Text)
    
    geocode_type = db.Column(db.Text)
    geocode_x = db.Column(db.Float)
    geocode_y = db.Column(db.Float)

######################
# ERRORS / REPORTING #
######################

class DorParcelError(db.Model):
    # Source fields
    id = db.Column(db.Integer, primary_key=True)
    objectid = db.Column(db.Integer)
    mapreg = db.Column(db.Text)
    stcod = db.Column(db.Integer)
    house = db.Column(db.Integer)
    suf = db.Column(db.Text)
    stex = db.Column(db.Text)
    stdir = db.Column(db.Text)
    stnam = db.Column(db.Text)
    stdes = db.Column(db.Text)
    stdessuf = db.Column(db.Text)
    unit = db.Column(db.Text)

    # Error fields
    level = db.Column(db.Text)
    reason = db.Column(db.Text)
    notes = db.Column(db.Text)

class DorParcelErrorPolygon(db.Model):
    # Source fields
    id = db.Column(db.Integer, primary_key=True)
    objectid = db.Column(db.Integer)
    mapreg = db.Column(db.Text)
    stcod = db.Column(db.Integer)
    house = db.Column(db.Integer)
    suf = db.Column(db.Text)
    stex = db.Column(db.Text)
    stdir = db.Column(db.Text)
    stnam = db.Column(db.Text)
    stdes = db.Column(db.Text)
    stdessuf = db.Column(db.Text)
    unit = db.Column(db.Text)
    shape = db.Column(Geometry(geometry_type='MULTIPOLYGON', srid=ENGINE_SRID))

    # Error fields
    reasons = db.Column(db.Text)
    reason_count = db.Column(db.Integer)
    notes = db.Column(db.Text)

class AddressError(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source_name = db.Column(db.Text)
    source_address = db.Column(db.Text)
    street_address = db.Column(db.Text)
    level = db.Column(db.Text)
    reason = db.Column(db.Text)
    notes = db.Column(db.Text)

class MultipleSegLine(db.Model):
    '''
    Lines connecting range addresses and segs wherever a range matches to 
    more than one street seg.
    '''
    id = db.Column(db.Integer, primary_key=True)
    street_address = db.Column(db.Text)
    parent_address = db.Column(db.Text)
    seg_id = db.Column(db.Integer)
    parcel_source = db.Column(db.Text)
    geom = db.Column(Geometry(geometry_type='LINESTRING', srid=ENGINE_SRID))
