"""Local metric projection for short distances in Toronto (metres, accurate to well under 1%).

GeoJSON coordinates are lng/lat; buffers, nearest-point and along-the-route distances need metres.
"""

import math

import numpy as np
import shapely

LAT = 43.7  # Toronto
SCALE = np.array([111_320 * math.cos(math.radians(LAT)), 110_540])


def to_metres(geometry):
    return shapely.transform(geometry, lambda xy: xy * SCALE)


def to_degrees(geometry):
    return shapely.transform(geometry, lambda xy: xy / SCALE)
