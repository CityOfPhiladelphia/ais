# from functools import partial
from six.moves.urllib.parse import urlparse
# import pyproj
# from shapely.wkt import loads as shp_loads, dumps as shp_dumps
# from shapely.ops import transform as shp_transform
from shapely.geometry import Point
from math import sin, cos, atan2, radians, pi, degrees

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
#     return f'"{text}"'

def parse_url(url):
    p = urlparse(url)
    comps = {
        'scheme':       p.scheme,
        'host':         p.hostname,
        'user':         p.username,
        'password':     p.password,
        'db_name':      p.path[1:] if p.path else None,
    }
    return comps

# class WktTransformer(object):
#     def __init__(self, from_srid, to_srid):
#         self.project = partial(
#             pyproj.transform,
#             pyproj.Proj('+init=EPSG:{from_srid}'),
#             pyproj.Proj('+init=EPSG:{to_srid}')
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


def project_shape(shape, from_srid, to_srid):
    from functools import partial
    import pyproj
    from shapely.ops import transform

    project = partial(
        pyproj.transform,
        # source coordinate system; preserve_units so that pyproj does not
        # assume meters
        pyproj.Proj(init=f'epsg:{from_srid}', preserve_units=True),
        # destination coordinate system
        pyproj.Proj(init=f'epsg:{to_srid}', preserve_units=True))

    return transform(project, shape)


def geom_to_shape(geom, from_srid, to_srid):
    from geoalchemy2.shape import to_shape
    shape = to_shape(geom) if geom is not None else None
    return shape
	#return project_shape(shape, from_srid, to_srid)


def interpolate_buffered(line, distance_ratio, _buffer):
	'''
	Interpolate along a line with a buffer at both ends.
	'''
	length = line.length
	buffered_length = length - (_buffer * 2)
	buffered_distance = distance_ratio * buffered_length
	absolute_distance = _buffer + buffered_distance
	return line.interpolate(absolute_distance)

def offset(line, point, distance, seg_side):
	# line = line[0]  # Get first part of multipart

	# Check for vertical line
	if line.coords[0][0] == line.coords[1][0]:
		pt_0 = line.coords[0]
		pt_1 = line.coords[1]
		upwards = True if pt_1[1] > pt_0[1] else False
		if (upwards and seg_side == 'R') or (not upwards and seg_side == 'L'):
			x_factor = 1
		else:
			x_factor = -1
		return Point([point.x + (distance * x_factor), point.y])

	assert None not in [line, point]
	assert distance > 0
	assert seg_side in ['L', 'R']

	xsect_x = point.x
	xsect_y = point.y
	coord_1 = None
	coord_2 = None

	# Find coords on either side of intersect point
	for i, coord in enumerate(line.coords[:-1]):
		coord_x, coord_y = coord
		next_coord = line.coords[i + 1]
		next_coord_x, next_coord_y = next_coord
		sandwich_x = coord_x < xsect_x < next_coord_x
		sandwich_y = coord_y <= xsect_y <= next_coord_y
		if sandwich_x or sandwich_y:
			coord_1 = coord
			coord_2 = next_coord
			break

	# Normalize coords to place in proper quadrant
	norm_x = next_coord[0] - coord[0]
	norm_y = next_coord[1] - coord[1]

	# Get angle of seg
	seg_angle = atan2(norm_y, norm_x)
	# print(f'seg angle: {degrees(seg_angle)}')

	# Get angle of offset line
	if seg_side == 'L':
		offset_angle = seg_angle + (pi / 2)
	else:
		offset_angle = seg_angle - (pi / 2)
	# print(f'offset angle: {degrees(offset_angle)}')

	# Get offset point
	delta_x = cos(offset_angle) * distance
	delta_y = sin(offset_angle) * distance
	x = xsect_x + delta_x
	y = xsect_y + delta_y
	return Point([x, y])
