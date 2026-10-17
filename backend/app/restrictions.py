"""Active City of Toronto road and sidewalk restrictions (Road Restrictions v3 open-data feed).

Used for ward report cards (closures in a ward) and trip alerts (closures near the route).
The feed is a few MB and takes seconds to download, so it is kept in memory and refreshed
in the background every 10 minutes (see feeds.py).
"""

import json
import re
import time

import httpx
from shapely.geometry import LineString, Point

from .feeds import Feed

URL = "https://secure.toronto.ca/opendata/cart/road_restrictions/v3?format=json"
SOURCE_URL = "https://open.toronto.ca/dataset/road-restrictions/"
TTL = 600
# The feed contains stray backslashes that are not valid JSON escapes.
_BAD_ESCAPE = re.compile(r'\\(?!["\\/bfnrtu])')


def parse(text: str, now_ms: float | None = None) -> list[dict]:
    """Restrictions in effect at `now_ms`, each with a Point or LineString geometry."""
    now_ms = now_ms if now_ms is not None else time.time() * 1000
    data = json.loads(_BAD_ESCAPE.sub(r"\\\\", text), strict=False)
    result = []
    for item in data.get("Closure", []):
        try:
            if int(item.get("expired") or 0) or not float(item["startTime"]) <= now_ms <= float(item["endTime"]):
                continue
            points = json.loads(f"[{item['geoPolyline']}]") if item.get("geoPolyline") else []
            if len(points) >= 2:
                geometry = LineString(points)
            else:
                geometry = Point(float(item["longitude"]), float(item["latitude"]))
        except (KeyError, TypeError, ValueError):
            continue
        description = f"{item.get('name') or ''} {item.get('description') or ''}".lower()
        result.append({
            "id": item.get("id"), "type": item.get("type"), "road": item.get("road"),
            "label": item.get("name") or item.get("road") or "Road restriction",
            "impact": item.get("maxImpact"), "sidewalk": "sidewalk" in description,
            "geometry": geometry,
        })
    return result


def _fetch() -> dict:
    response = httpx.get(URL, timeout=20, headers={"User-Agent": "ClearPath-Toronto/0.1"})
    response.raise_for_status()
    return {"available": True, "items": parse(response.text)}


FEED = Feed("road-restrictions", _fetch, TTL)


def active() -> dict:
    """{available, items}. available=False, never an exception, when the feed has not loaded."""
    return FEED.get() or {"available": False, "items": []}
