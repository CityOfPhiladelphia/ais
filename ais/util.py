# from functools import partial
# from six.moves.urllib.parse import urlparse
# import pyproj
# from shapely.wkt import loads as shp_loads, dumps as shp_dumps
# from shapely.ops import transform as shp_transform

def parity_for_num(num):
    if num % 2 == 0:
        return 'E'
    return 'O'

def parity_for_range(low, high):
    # Handle null ranges
    if high in [None, 0]:
        return 'U'
    parity_low = parity_for_num(low)
    if parity_low == parity_for_num(high):
        return parity_low
    return 'B'

# def dbl_quote(text):
#     """Place double quotes around a string."""
#     return '"{}"'.format(text)

# def parse_url(url):
#     p = urlparse(url)
#     comps = {
#         'scheme':       p.scheme,
#         'host':         p.hostname,
#         'user':         p.username,
#         'password':     p.password,
#         'db_name':      p.path[1:] if p.path else None,
#     }
#     return comps

# class WktTransformer(object):
#     def __init__(self, from_srid, to_srid):
#         self.project = partial(
#             pyproj.transform,
#             pyproj.Proj('+init=EPSG:{}'.format(from_srid)),
#             pyproj.Proj('+init=EPSG:{}'.format(to_srid))
#         )

#     def transform(self, from_wkt):
#         from_shp = shp_loads(from_wkt)
#         shp_t = shp_transform(self.project, from_shp)
#         return shp_dumps(shp_t)


class FilteredDict (dict):
    """
    A `dict` that excludes values that don't match some condition function. If
    the condition function is `None`, the identity is assumed. That is, all
    values that are false are excluded.
    """
    def __init__(self, cond, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.cond = cond or (lambda value: value)
        for key, val in list(self.items()):
            if not cond(val):
                del self[key]

    def __setitem__(self, key, value):
        if self.cond(value):
            super().__setitem__(key, value)
        elif key in self:
            del self[key]


class NotNoneDict (FilteredDict):
    """
    A `dict` that excludes values that are `None`.
    """
    def __init__(self, *args, **kwargs):
        not_none = (lambda value: value is not None)
        super().__init__(not_none, *args, **kwargs)


def geom_to_shape(geom, from_srid, to_srid):
    from geoalchemy2.shape import to_shape
    shape = to_shape(geom)

    from functools import partial
    import pyproj
    from shapely.ops import transform

    project = partial(
        pyproj.transform,
        # source coordinate system; preserve_units so that pyproj does not
        # assume meters
        pyproj.Proj(init='epsg:{}'.format(from_srid), preserve_units=True),
        # destination coordinate system
        pyproj.Proj(init='epsg:{}'.format(to_srid), preserve_units=True))

    return transform(project, shape)
