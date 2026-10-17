"""Shared barrier queries for map display and routing constraints."""

import json
import math
from pathlib import Path

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout
from shapely.geometry import box, shape

from .config import settings

TORONTO_BBOX = (-79.65, 43.55, -79.1, 43.9)
FIXTURE_PATH = Path(__file__).parent / "data" / "barriers.json"
_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(settings.database_url, min_size=1, max_size=5,
                               timeout=3, kwargs={"connect_timeout": 3}, open=True)
    return _pool


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    try:
        west, south, east, north = map(float, value.split(","))
        if not all(math.isfinite(number) for number in (west, south, east, north)):
            raise ValueError
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError
        return west, south, east, north
    except ValueError:
        raise HTTPException(422, detail={
            "code": "invalid_bbox", "message": "Use bbox=west,south,east,north with valid longitude and latitude bounds.",
        }) from None


def query_features(bounds=None, kind: str | None = None) -> list[dict]:
    if settings.barrier_source == "fixtures":
        features = json.loads(FIXTURE_PATH.read_text())["features"]
    else:
        try:
            with get_pool().connection() as connection:
                with connection.cursor(row_factory=dict_row) as cursor:
                    cursor.execute("""
                        SELECT id, source, kind, status, verification, blocks_route,
                               opened_at, ward_id, source_url,
                               ST_AsGeoJSON(COALESCE(avoidance_geom, geom)) AS geometry
                        FROM barriers
                        WHERE closed_at IS NULL AND status = 'open'
                          AND ST_Intersects(COALESCE(avoidance_geom, geom), ST_MakeEnvelope(%s, %s, %s, %s, 4326))
                          AND (%s::text IS NULL OR kind = %s)
                        ORDER BY id
                    """, (*(bounds or TORONTO_BBOX), kind, kind))
                    features = []
                    for row in cursor.fetchall():
                        geometry = json.loads(row.pop("geometry"))
                        row["opened_at"] = row["opened_at"].isoformat()
                        features.append({"type": "Feature", "geometry": geometry, "properties": row})
        except (psycopg.Error, PoolTimeout):
            raise HTTPException(503, detail={
                "code": "barrier_data_unavailable", "message": "Barrier data is unavailable. Try again shortly.",
            }) from None

    return [feature for feature in features
            if feature["properties"].get("status") == "open"
            and feature["properties"].get("closed_at") is None
            and (kind is None or feature["properties"]["kind"] == kind)
            and (bounds is None or shape(feature["geometry"]).intersects(box(*bounds)))]


def route_bounds(coordinates) -> tuple[float, float, float, float]:
    longitudes, latitudes = zip(*[(point[0], point[1]) for point in coordinates])
    return (max(-180, min(longitudes) - .01), max(-90, min(latitudes) - .01),
            min(180, max(longitudes) + .01), min(90, max(latitudes) + .01))


def blockers(features: list[dict]) -> list[dict]:
    result = []
    for feature in features:
        properties = feature["properties"]
        if not (properties.get("status") == "open"
                and properties.get("verification") == "verified"
                and properties.get("blocks_route") is True):
            continue
        geometry = shape(feature["geometry"])
        if geometry.geom_type in ("Polygon", "MultiPolygon") and geometry.is_valid and not geometry.is_empty:
            result.append(feature)
    return result


