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


