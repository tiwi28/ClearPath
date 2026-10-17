"""Rider reports from trips, and the spots they add up to.

One "blocked" report shows the spot to other riders as unverified. Two or more different
devices reporting it blocked within 48 h, with no newer "clear" report, confirm it: it then
becomes a small avoid-area that routing treats like a verified barrier. Spots expire 48 h
after the last blocked report.

Recent reports are kept in memory (refreshed every 30 s, and right after each new report), so
barrier queries never wait on the database, and an unreachable database costs nothing.
"""

import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row
from psycopg_pool import PoolTimeout
from shapely.geometry import MultiPoint, Point, mapping

from . import geo
from .feeds import Feed

WINDOW = timedelta(hours=48)
CLUSTER_M = 20       # reports this close together describe the same spot
AVOID_RADIUS_M = 12  # size of a confirmed spot's avoid-area
CONFIRMATIONS = 2    # different devices needed before routing avoids a spot
RATE_LIMIT = 10      # reports per device per hour
IP_RATE_LIMIT = 30   # reports per network address per hour (device ids are made up by the client)
KINDS = ("blocked_sidewalk", "snow_ice", "construction", "elevator_out", "other")
LABELS = {"blocked_sidewalk": "Blocked sidewalk", "snow_ice": "Snow or ice", "construction": "Construction",
          "elevator_out": "Elevator out", "other": "Reported problem"}


def _pool():
    from .barriers import get_pool  # barriers imports this module, so import lazily
    return get_pool()


_by_address: dict[str, deque] = defaultdict(deque)
_address_lock = threading.Lock()


def _allow_address(address: str) -> bool:
    """In-memory sliding-window limit per network address."""
    now = time.time()
    with _address_lock:
        stamps = _by_address[address]
        while stamps and now - stamps[0] > 3600:
            stamps.popleft()
        if len(stamps) >= IP_RATE_LIMIT:
            return False
        stamps.append(now)
        return True


def record(device_id: str, kind: str, state: str, profile: str | None, lng: float, lat: float,
           address: str = "unknown") -> dict:
    if not _allow_address(address):
        raise HTTPException(429, detail={"code": "too_many_reports", "message": "Thanks. You've sent a lot of reports this hour; try again later."})
    try:
        with _pool().connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM rider_reports WHERE device_id = %s AND created_at > now() - interval '1 hour'",
                           (device_id,))
            if cursor.fetchone()[0] >= RATE_LIMIT:
                raise HTTPException(429, detail={"code": "too_many_reports", "message": "Thanks. You've sent a lot of reports this hour; try again later."})
            cursor.execute("""INSERT INTO rider_reports (device_id, kind, state, profile, geom)
                              VALUES (%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)) RETURNING id, created_at""",
                           (device_id, kind, state, profile, lng, lat))
            report_id, created = cursor.fetchone()
    except (psycopg.Error, PoolTimeout):
        raise HTTPException(503, detail={"code": "reports_unavailable", "message": "Reports can't be saved right now. Try again shortly."}) from None
    REPORTS.refresh(force=True)  # the next plan sees this report straight away
    return {"id": report_id, "created_at": created.isoformat()}


def _fetch_recent() -> list[dict]:
    with _pool().connection() as connection, connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute("""SELECT id, created_at, device_id, kind, state, ST_X(geom) AS lng, ST_Y(geom) AS lat
                          FROM rider_reports WHERE created_at > now() - %s ORDER BY created_at""", (WINDOW,))
        return cursor.fetchall()


REPORTS = Feed("rider-reports", _fetch_recent, ttl=30)


def recent(bounds) -> list[dict]:
    """Reports from the last 48 h inside bounds. Empty when the database is unreachable."""
    west, south, east, north = bounds
    return [r for r in REPORTS.get() or [] if west <= r["lng"] <= east and south <= r["lat"] <= north]


def spots(reports: list[dict], now: datetime | None = None) -> list[dict]:
    """Group reports into spots and return the open ones as barrier-shaped GeoJSON features."""
    now = now or datetime.now(timezone.utc)
    clusters: list[dict] = []
    for report in sorted(reports, key=lambda r: r["created_at"]):
        point = geo.to_metres(Point(report["lng"], report["lat"]))
        cluster = next((c for c in clusters if c["centre"].distance(point) <= CLUSTER_M), None)
        if cluster is None:
            cluster = {"centre": point, "reports": []}
            clusters.append(cluster)
        cluster["reports"].append({**report, "point": point})
        blocked = [r["point"] for r in cluster["reports"] if r["state"] == "blocked"] or [point]
        cluster["centre"] = MultiPoint(blocked).centroid

    features = []
    for cluster in clusters:
        blocked = [r for r in cluster["reports"] if r["state"] == "blocked" and now - r["created_at"] <= WINDOW]
        clears = [r for r in cluster["reports"] if r["state"] == "clear"]
        if not blocked or (clears and max(c["created_at"] for c in clears) >= max(b["created_at"] for b in blocked)):
            continue
        devices = {r["device_id"] for r in blocked}
        confirmed = len(devices) >= CONFIRMATIONS
        kind = max(set(r["kind"] for r in blocked), key=[r["kind"] for r in blocked].count)
        centre = cluster["centre"]
        geometry = geo.to_degrees(centre.buffer(AVOID_RADIUS_M, 8) if confirmed else centre)
        features.append({"type": "Feature", "geometry": mapping(geometry), "properties": {
            "id": -min(r["id"] for r in blocked),  # negative ids never collide with City barrier ids
            "source": "rider", "kind": kind, "label": LABELS.get(kind, "Reported problem"),
            "status": "open", "verification": "rider_confirmed" if confirmed else "reported",
            "blocks_route": confirmed, "reports": len(blocked), "devices": len(devices),
            "opened_at": min(r["created_at"] for r in blocked).isoformat(),
            "last_reported": max(r["created_at"] for r in blocked).isoformat(),
        }})
    return features


def features(bounds) -> list[dict]:
    return spots(recent(bounds))
