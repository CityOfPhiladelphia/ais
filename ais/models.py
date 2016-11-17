import copy
import re
from flask.ext.sqlalchemy import BaseQuery
from geoalchemy2.types import Geometry
from sqlalchemy import or_
from sqlalchemy.orm import aliased
from sqlalchemy.exc import NoSuchTableError
from ais import app, app_db as db
from ais.util import *
from pprint import pprint

Parser = app.config['PARSER']
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

class StreetIntersection(db.Model):
    """An intersection of street centerlines."""
    id = db.Column(db.Integer, primary_key=True)
    street_code_1 = db.Column(db.Text)
    street_code_2 = db.Column(db.Text)
    int_ids = db.Column(db.Text)
    geom = db.Column(Geometry(geometry_type='POINT', srid=ENGINE_SRID))

    # def __init__(self, *args, **kwargs):
    #     assert len(args) > 0
    #     arg = args[0]
    #
    #     if isinstance(arg, str):
    #         p = parser.parse(arg)
    #     elif isinstance(arg, dict):
    #         p = arg
    #     else:
    #         raise ValueError('Not an address')
    #
    #     if p['type'] != 'intersection_addr':
    #         raise ValueError('Not an intersection')
    #
    #     c = p['components']
    #
    #     # TEMP: Passyunk doesn't raise an error if the street name
    #     # is missing for an address, so check here and do it manually.
    #     if c['street']['name'] is None:
    #         raise ValueError('No street name')
    #
    #     # TEMP: Passyunk doesn't raise an error if the address high is
    #     # lower than the address low.
    #     high_num_full = c['address']['high_num_full']
    #     if high_num_full and high_num_full < c['address']['low_num']:
    #         raise ValueError('Invalid range address')
    #
    #     kwargs = {
    #         'address_low': c['address']['low_num'],
    #         'street_1_full': c['street']['full'],
    #         'street_1_name': c['street']['name'],
    #         'street_1_code': c['street']['street_code'],
    #         'street_1_predir': c['street']['full'],
    #         'street_1_postdir': c['street']['name'],
    #         'street_1_suffix': c['street']['street_code'],
    #         'street_2_full': c['street_2']['full'],
    #         'street_2_name': c['street_2']['name'],
    #         'street_2_code': c['street_2']['street_code'],
    #         'street_2_predir': c['street_2']['full'],
    #         'street_2_postdir': c['street_2']['name'],
    #         'street_2_suffix': c['street_2']['street_code'],
    #     }
    #
    #     super(StreetIntersection, self).__init__(**kwargs)


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
    'zip_code',
    'zip_4',
]

class AddressQuery(BaseQuery):
    """A query class that knows how to sort addresses"""
    def order_by_address(self):
        return self.order_by(Address.street_name,
                             Address.street_suffix,
                             Address.street_predir,
                             Address.street_postdir,
                             Address.address_low,
                             Address.address_high,
                             Address.unit_type.nullsfirst(),
                             Address.unit_num.nullsfirst())

    def filter_by_owner(self, *owner_parts):
        query = self.join(AddressProperty, AddressProperty.street_address==Address.street_address)\
            .join(OpaProperty, OpaProperty.account_num==AddressProperty.opa_account_num)

        for part in owner_parts:
            query = query.filter(OpaProperty.owners.like('%{}%'.format(part)))
        return query


class Address(db.Model):
    """A street address with parsed components."""
    query_class = AddressQuery

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

    geocodes = db.relationship(
        'Geocode',
        primaryjoin='foreign(Geocode.street_address) == Address.street_address',
        lazy='joined')

    # zip_info = db.relationship(
    #     'AddressZip',
    #     primaryjoin='foreign(AddressZip.street_address) == Address.street_address',
    #     lazy='joined',
    #     uselist=False)

    pwd_parcel = db.relationship(
        'PwdParcel',
        primaryjoin='foreign(PwdParcel.street_address) == Address.street_address',
        lazy='joined',
        uselist=False)
    dor_parcel = db.relationship(
        'DorParcel',
        primaryjoin='foreign(DorParcel.street_address) == Address.street_address',
        lazy='joined',
        uselist=False)
    opa_property = db.relationship(
        'OpaProperty',
        primaryjoin='foreign(OpaProperty.street_address) == Address.street_address',
        lazy='joined',
        uselist=False)

    def __init__(self, *args, **kwargs):

        assert len(args) > 0
        arg = args[0]

        if isinstance(arg, str):
            p = parser.parse(arg)
        elif isinstance(arg, dict):
            p = arg
        else:
            raise ValueError('Not an address')

        if p['type'] != 'address':
            raise ValueError('Not an address')

        c = p['components']

        # TEMP: Passyunk doesn't raise an error if the street name
        # is missing for an address, so check here and do it manually.
        if c['street']['name'] is None:
            raise ValueError('No street name')

        # TEMP: Passyunk doesn't raise an error if the address high is
        # lower than the address low.
        high_num_full = c['address']['high_num_full']
        if high_num_full and high_num_full < c['address']['low_num']:
            raise ValueError('Invalid range address')

        kwargs = {
            'address_low':          c['address']['low_num'],
            'address_low_suffix':   c['address']['addr_suffix'],           # passyunk change
            'address_low_frac':     c['address']['fractional'],            # passyunk change
            'address_high':         c['address']['high_num_full'],
            'street_predir':        c['street']['predir'],
            'street_name':          c['street']['name'],
            'street_suffix':        c['street']['suffix'],
            'street_postdir':       c['street']['postdir'],
            'unit_type':            c['address_unit']['unit_type'],                # passyunk change
            'unit_num':             c['address_unit']['unit_num'],                 # passyunk change
            'street_full':          c['street']['full'],
            'street_address':       c['street_address'],
            'zip_code':             c['mailing']['zipcode'],
            'zip_4':                c['mailing']['zip4'],
        }

        super(Address, self).__init__(**kwargs)

    def __str__(self):
        return 'Address: {}'.format(self.street_address)

    def __repr__(self):
        return self.__str__()

    def __iter__(self):
        for key in ADDRESS_FIELDS:
            yield (key, getattr(self, key))

    @property
    def geocode(self):
        """Returns the "best" geocoded value"""
        if not self.geocodes:
            return None

        priority = {
            'pwd_parcel': 4,
            'dor_parcel': 3,
            'true_range': 2,
            'centerline': 1,
        }
        return max(self.geocodes, key=lambda g: priority[g.geocode_type])

    def get_geocode(self, geocode_type):
        for g in self.geocodes:
            if g.geocode_type == geocode_type:
                return g
        return None

    # @property
    # def zip_code(self):
    #     #return self.zip_info.zip_range.zip_code if self.zip_info else None
    #
    # @property
    # def zip_4(self):
    #     #return self.zip_info.zip_range.zip_4 if self.zip_info else None


    @property
    def pwd_parcel_id(self):
        return self.pwd_parcel.parcel_id if self.pwd_parcel else None

    @property
    def dor_parcel_id(self):
        return self.dor_parcel.parcel_id if self.dor_parcel else None

    @property
    def opa_account_num(self):
        return self.opa_property.account_num if self.opa_property else None

    @property
    def opa_owners(self):
        return self.opa_property.owners if self.opa_property else None

    @property
    def opa_address(self):
        return self.opa_property.source_address if self.opa_property else None

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
        if self.address_high:
            address_full += '-' + str(self.address_high)[-2:]
        if self.address_low_frac:
            address_full += ' ' + self.address_low_frac
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
    def is_basic_range(self):
        """
        Determines if an address is a basic range, i.e. it has an address
        high but no other secondary components like suffix, fractional, or unit.
        """
        is_range = self.address_high is not None
        non_basic_comps = [
            self.address_low_suffix,
            self.address_low_frac,
            self.unit_type,
        ]
        is_basic = all(comp is None for comp in non_basic_comps)
        return is_range and is_basic

    @property
    def child_addresses(self):
        """Returns a list of individual street addresses for a range"""
        address_low_re = re.compile('^{}'.format(self.address_low))
        address_high_re = re.compile('-\d+')
        child_addresses = []
        for child_num in self.child_nums:
            child_num = str(child_num)
            child_street_address = address_low_re.sub(child_num, \
                                                      self.street_address)
            child_street_address = address_high_re.sub('', child_street_address)
            child_address = Address(child_street_address)
            child_addresses.append(child_address)
        return child_addresses

    @property
    def child_nums(self):
        """Returns a list of individual address nums for a range"""
        if not self.is_basic_range:
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
    """
    Current tags in the database are:
    * li_address_key
    * info_resident (private)
    * info_company (private)
    * voter_name (private?)
    * pwd_account_num

    """
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
    """
    relationship choices:
    * in range -- address falls in an official address range
    * has base --
    * has generic unit --
    * matches unit --

    74-78 LAUREL ST UNIT 6
    """
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
    street_address = db.Column(db.Text) #, db.ForeignKey('address.street_address'))
    opa_account_num = db.Column(db.Text) #, db.ForeignKey('opa_property.account_num'))
    match_type = db.Column(db.Text)

class AddressZip(db.Model):
    '''
    Stores information about the relationship between addresses and ZIP ranges.
    '''
    id = db.Column(db.Integer, primary_key=True)
    street_address = db.Column(db.Text)
    usps_id = db.Column(db.Text)
    match_type = db.Column(db.Text)

    zip_range = db.relationship(
        'ZipRange',
        primaryjoin='foreign(ZipRange.usps_id) == AddressZip.usps_id',
        lazy='joined',
        uselist=False)



#############
# GEOCODING #
#############

class Geocode(db.Model):
    """
    Values for `geocode_type` are:
    * pwd_parcel
    * dor_parcel
    * true_range
    * centerline

    Generally, values should be respected in that order. Centerline
    can usually be disregarded.

    """
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

    layer = db.relationship(
        'ServiceAreaLayer',
        primaryjoin='foreign(ServiceAreaLayer.layer_id) == ServiceAreaPolygon.layer_id',
        lazy='joined',
        uselist=False,
    )

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

class AddressSummaryQuery(BaseQuery):
    """A query class that knows how to sort addresses"""
    def order_by_address(self):
        return self.order_by(AddressSummary.street_name,
                             AddressSummary.street_suffix,
                             AddressSummary.street_predir,
                             AddressSummary.street_postdir,
                             AddressSummary.address_low,
                             AddressSummary.address_high,
                             AddressSummary.unit_type.nullsfirst(),
                             AddressSummary.unit_num.nullsfirst())

    def filter_by_owner(self, *owner_parts):
        query = self
        for part in owner_parts:
            query = query.filter(AddressSummary.opa_owners.like('%{}%'.format(part)))
        return query

    def filter_by_unit_type(self, unit_type):
        if not unit_type:
            return self

        synonymous_unit_types = ('APT', 'UNIT', '#', 'STE')
        if unit_type in synonymous_unit_types:
            return self.filter(
                AddressSummary.unit_type.in_(synonymous_unit_types))
        else:
            return self.filter_by(unit_type=unit_type)

    def include_child_units(self, should_include=True, is_range=False, is_unit=False):
        """
        Find units of a set of addresses. If an address is a part of a ranged
        address, find all units in that parent range.
        """
        if not should_include:
            return self

        # If it's a unit, don't waste time with additional queries.
        if is_unit:
            return self

        # If the query is for ranged addresses only, then use the entire set of
        # addresses as parent addresses; use an empty set as addresses with no
        # parent (non-child addresses).
        if is_range:
            range_parent_addresses = self\
                .with_entities(AddressSummary.street_address)

            non_child_addresses = self\
                .with_entities(AddressSummary.street_address)\
                .filter(False)

        # If the query is not for ranged addresses, handle the case where more
        # than one address may have been matched (e.g., the N and S variants
        # along a street), but some are children of ranged addresses and some
        # are not.
        else:
            range_parent_addresses = self\
                .join(AddressLink, AddressLink.address_1 == AddressSummary.street_address)\
                .filter(AddressLink.relationship == 'in range')\
                .with_entities(AddressLink.address_2)

            non_child_addresses = self\
                .outerjoin(AddressLink, AddressLink.address_1 == AddressSummary.street_address)\
                .filter(AddressLink.relationship == None)\
                .with_entities(AddressSummary.street_address)

        # For the parent addresses, find all the child addresses within the
        # ranges.
        range_child_addresses = AddressLink.query\
            .filter(AddressLink.relationship == 'in range')\
            .filter(AddressLink.address_2.in_(range_parent_addresses.subquery()))\
            .with_entities(AddressLink.address_1)

        # For both the range-child and non-child address sets, get all the units
        # and union them on to the original set of addresses.
        range_child_units = AddressSummary.query\
            .join(AddressLink, AddressLink.address_1 == AddressSummary.street_address)\
            .filter(AddressLink.relationship == 'has base')\
            .filter( AddressLink.address_2.in_(range_child_addresses.subquery()))

        non_child_units = AddressSummary.query\
            .join(AddressLink, AddressLink.address_1 == AddressSummary.street_address)\
            .filter(AddressLink.relationship == 'has base')\
            .filter( AddressLink.address_2.in_(non_child_addresses.subquery()))

        return self.union(range_child_units).union(non_child_units)

    def exclude_children(self, should_exclude=True):
        if not should_exclude:
            return self

        return self\
            .outerjoin(AddressLink, AddressLink.address_1 == AddressSummary.street_address, aliased=True)\
            .filter(
                # Get rid of anything with a relationship of 'in range',
                # 'has generic unit', or 'matches unit'.
                (AddressLink.relationship == 'has base') |
                (AddressLink.relationship == None)
            )

    def exclude_non_opa(self, should_exclude=True):
        if should_exclude:
            # Filter for addresses that have OPA numbers. As a result of
            # aggressive assignment of OPA numbers to units of a property,
            # also filter out anything that is a unit and has an OPA number
            # equal to its base address.

            BaseAddressSummary = aliased(AddressSummary)

            return self\
                .filter(AddressSummary.opa_account_num != '')\
                .outerjoin(AddressLink, AddressLink.address_1 == AddressSummary.street_address, aliased=True)\
                .outerjoin(BaseAddressSummary, AddressLink.address_2 == BaseAddressSummary.street_address, from_joinpoint=True)\
                .filter(~(
                    # Get rid of anything where the OPA account number matches
                    # it's base's OPA account number. In the case where the
                    # address does not have a base, the base num will be None.
                    (AddressSummary.unit_type != '') &
                    (AddressSummary.opa_account_num == BaseAddressSummary.opa_account_num)
                ))

        else:
            return self

try:
    class ServiceAreaSummary(db.Model):
        __table__ = db.Table('service_area_summary',
                             db.MetaData(bind=db.engine),
                             autoload=True)
except NoSuchTableError:
    ServiceAreaSummary = None
    # if table hasn't been created yet, suppress error
    pass

class AddressSummary(db.Model):
    query_class = AddressSummaryQuery

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
    usps_bldgfirm = db.Column(db.Text)
    usps_type = db.Column(db.Text)
    election_block_id = db.Column(db.Text)
    election_precinct = db.Column(db.Text)

    # Foreign keys
    street_code = db.Column(db.Integer)
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

    geocodes = db.relationship(
        'Geocode',
        primaryjoin='foreign(Geocode.street_address) == AddressSummary.street_address',
        lazy='select')

    tags = db.relationship(
        'AddressTag',
        primaryjoin='foreign(AddressTag.street_address) == AddressSummary.street_address',
        lazy='select')

    if ServiceAreaSummary:
        service_areas = db.relationship(
            'ServiceAreaSummary',
            primaryjoin='foreign(ServiceAreaSummary.street_address) == AddressSummary.street_address',
            lazy='joined',
            uselist=False)

    # zip_info = db.relationship(
    #     'AddressZip',
    #     primaryjoin='foreign(AddressZip.street_address) == AddressSummary.street_address',
    #     lazy='select',
    #     uselist=False)

    pwd_parcel = db.relationship(
        'PwdParcel',
        primaryjoin='foreign(PwdParcel.street_address) == AddressSummary.street_address',
        lazy='select',
        uselist=False)
    dor_parcel = db.relationship(
        'DorParcel',
        primaryjoin='foreign(DorParcel.street_address) == AddressSummary.street_address',
        lazy='select',
        uselist=False)
    opa_property = db.relationship(
        'OpaProperty',
        primaryjoin='foreign(OpaProperty.street_address) == AddressSummary.street_address',
        lazy='select',
        uselist=False)

    __table_args__ = (
        db.Index('address_summary_opa_account_num_idx', 'opa_account_num', postgresql_using='btree'),
        db.Index('address_summary_sort_idx', street_name, street_suffix, street_predir, street_postdir, address_low, address_high, unit_num, postgresql_using='btree')
    )

    @property
    def geocode(self):
        """Returns the "best" geocoded value"""
        if not self.geocodes:
            return None

        priority = {
            'pwd_parcel': 4,
            'dor_parcel': 3,
            'true_range': 2,
            'centerline': 1,
        }
        return max(self.geocodes, key=lambda g: priority[g.geocode_type])

    def get_geocode(self, geocode_type):
        for g in self.geocodes:
            if g.geocode_type == geocode_type:
                return g
        return None

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