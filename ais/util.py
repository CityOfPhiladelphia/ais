"""Shared spatial, URL, and address utility helpers."""

from functools import lru_cache
from math import atan2, cos, pi, sin
from urllib.parse import urlparse

from shapely.geometry import Point


def parity_for_num(num):
    return "E" if num % 2 == 0 else "O"


def parity_for_range(low, high):
    if high in (None, 0):
        return "U"
    parity_low = parity_for_num(low)
    if parity_low == parity_for_num(high):
        return parity_low
    return "B"


def unwrap_secret(value) -> str:
    """Extract the raw string from a pydantic SecretStr (or pass through a plain str)."""
    if value is None:
        return ""
    getter = getattr(value, "get_secret_value", None)
    return getter() if callable(getter) else str(value)


def parse_url(url):
    p = urlparse(unwrap_secret(url))
    return {
        "scheme": p.scheme,
        "host": p.hostname,
        "port": p.port,
        "user": p.username,
        "password": p.password,
        "db_name": p.path[1:] if p.path else None,
    }


def redact_url(url) -> str:
    """Return a log-safe DB URL with any embedded password replaced by '***'."""
    p = urlparse(unwrap_secret(url))
    host = p.hostname or ""
    port = f":{p.port}" if p.port else ""
    auth = f"{p.username}:***@" if p.username else ""
    return f"{p.scheme}://{auth}{host}{port}{p.path}"


class FilteredDict(dict):
    """A dict that excludes values failing a predicate (defaults to truthiness)."""

    def __init__(self, cond, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cond = cond or (lambda value: value)
        for key, val in list(self.items()):
            if not self.cond(val):
                del self[key]

    def __setitem__(self, key, value):
        if self.cond(value):
            super().__setitem__(key, value)
        elif key in self:
            del self[key]


class NotNoneDict(FilteredDict):
    """A dict that excludes values that are None."""

    def __init__(self, *args, **kwargs):
        super().__init__(lambda value: value is not None, *args, **kwargs)


@lru_cache(maxsize=16)
def _get_transformer(from_srid: int, to_srid: int):
    import pyproj

    return pyproj.Transformer.from_crs(
        f"EPSG:{int(from_srid)}",
        f"EPSG:{int(to_srid)}",
        always_xy=True,
    )


def project_shape(shape, from_srid, to_srid):
    import numpy as np
    import shapely

    if int(from_srid) == int(to_srid):
        return shape
    transformer = _get_transformer(int(from_srid), int(to_srid))

    def _transform_coords(coords):
        xs, ys = transformer.transform(coords[:, 0], coords[:, 1])
        return np.column_stack((xs, ys))

    return shapely.transform(shape, _transform_coords)


def geom_to_shape(geom, from_srid, to_srid):
    from geoalchemy2.shape import to_shape

    return to_shape(geom) if geom is not None else None


def interpolate_buffered(line, distance_ratio, _buffer):
    """Interpolate along a line with a buffer at both ends."""
    length = line.length
    buffered_length = length - (_buffer * 2)
    buffered_distance = distance_ratio * buffered_length
    absolute_distance = _buffer + buffered_distance
    return line.interpolate(absolute_distance)


def offset(line, point, distance, seg_side):
    """Offset a point perpendicular to a line segment by distance on seg_side ('L' or 'R')."""
    if line.coords[0][0] == line.coords[1][0]:
        pt_0 = line.coords[0]
        pt_1 = line.coords[1]
        upwards = pt_1[1] > pt_0[1]
        x_factor = 1 if (upwards and seg_side == "R") or (not upwards and seg_side == "L") else -1
        return Point([point.x + (distance * x_factor), point.y])

    assert None not in (line, point)
    assert distance > 0
    assert seg_side in ("L", "R")

    xsect_x = point.x
    xsect_y = point.y
    coord = line.coords[0]
    next_coord = line.coords[1]

    for i, c in enumerate(line.coords[:-1]):
        coord_x, coord_y = c
        nc = line.coords[i + 1]
        next_coord_x, next_coord_y = nc
        sandwich_x = coord_x < xsect_x < next_coord_x
        sandwich_y = coord_y <= xsect_y <= next_coord_y
        if sandwich_x or sandwich_y:
            coord = c
            next_coord = nc
            break

    norm_x = next_coord[0] - coord[0]
    norm_y = next_coord[1] - coord[1]
    seg_angle = atan2(norm_y, norm_x)
    offset_angle = seg_angle + (pi / 2) if seg_side == "L" else seg_angle - (pi / 2)

    x = xsect_x + cos(offset_angle) * distance
    y = xsect_y + sin(offset_angle) * distance
    return Point([x, y])
