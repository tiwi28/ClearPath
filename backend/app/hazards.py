"""Alerts ahead on a trip: what the rider will meet, and how far along the route it is.

Combines verified barriers, rider reports, the barrier forecast, City road restrictions, the
route's unconfirmed stretches and TTC elevator outages, each placed by its distance along the
route so the app can announce it shortly before the rider gets there.
"""

from fastapi import HTTPException
from shapely.geometry import LineString, Point, shape

from . import barriers, forecast, geo, restrictions, risk, ttc

NEAR_M = 25  # how close to the path a barrier or closure must be to matter


def _along(line_m: LineString, geometry_m) -> float:
    """Distance along the route of the first place the route comes near or enters `geometry_m`."""
    near = line_m.intersection(geometry_m.buffer(NEAR_M))
    points = list(getattr(near, "coords", [])) or [c for part in getattr(near, "geoms", []) for c in part.coords]
    if not points:
        return line_m.project(geometry_m.centroid)
    return min(line_m.project(Point(p)) for p in points)


def find(coordinates, day=None, stations=(), unverified=()) -> list[dict]:
    line = LineString(coordinates)
    line_m = geo.to_metres(line)
    corridor = line_m.buffer(NEAR_M)
    found: list[dict] = []

    for feature in barriers.query_features(barriers.route_bounds(coordinates)):
        props = feature["properties"]
        geometry_m = geo.to_metres(shape(feature["geometry"]))
        if not corridor.intersects(geometry_m):
            continue
        rider = props.get("source") == "rider"
        blocking = props.get("blocks_route") is True and props.get("verification") in ("verified", "rider_confirmed")
        label = props.get("label") or props.get("kind", "Barrier").replace("_", " ").capitalize()
        found.append({
            "id": f"barrier-{props['id']}", "kind": "rider_report" if rider else "barrier",
            "label": f"{label}, reported by {props['devices']} rider{'s' if props['devices'] != 1 else ''}" if rider else label,
            "severity": "blocker" if blocking else "warning", "source": "riders" if rider else props.get("source", "city"),
            "confirmable": True, "at_m": _along(line_m, geometry_m),
            "lnglat": list(geo.to_degrees(geometry_m.centroid).coords[0]),
        })

    try:
        cells = forecast.predict(day)["features"]
    except HTTPException:
        cells = []
    for cell in cells:
        if cell["properties"]["risk"] < risk.HIGH_RISK:
            continue
        geometry_m = geo.to_metres(shape(cell["geometry"]))
        if not line_m.intersects(geometry_m):
            continue
        at = _along(line_m, geometry_m)
        found.append({
            "id": f"risk-{cell['properties']['cell']}", "kind": "forecast", "severity": "info", "source": "forecast",
            "label": f"Higher chance of a sidewalk barrier for the next stretch ({round(cell['properties']['risk'] * 100)}% forecast)",
            "confirmable": True, "at_m": at, "lnglat": list(geo.to_degrees(line_m.interpolate(at)).coords[0]),
        })

    feed = restrictions.active()
    for item in feed["items"] if feed["available"] else []:
        geometry_m = geo.to_metres(item["geometry"])
        if not corridor.intersects(geometry_m):
            continue
        closed = item["type"] == "ROAD_CLOSED"
        found.append({
            "id": f"closure-{item['id']}", "kind": "closure", "source": "city",
            "label": f"{'Road closed' if closed else 'Roadwork'}: {item['label']}"[:140],
            "severity": "warning" if item["sidewalk"] or closed else "info",
            "confirmable": True, "at_m": _along(line_m, geometry_m),
            "lnglat": list(geo.to_degrees(line_m.interpolate(_along(line_m, geometry_m))).coords[0]),
        })

    for gap in unverified:
        at = 0.0 if gap["end"] == "start" else max(0.0, line_m.length - gap["length_m"])
        found.append({
            "id": f"gap-{gap['end']}", "kind": "unverified", "severity": "warning", "source": "clearpath",
            "label": f"The next {round(gap['length_m'])} m isn't confirmed step-free. Check the entrance.",
            "confirmable": True, "at_m": at, "lnglat": list(geo.to_degrees(line_m.interpolate(at)).coords[0]),
        })

    alerts = ttc.live_alerts() if stations else {"outages": []}
    for stop in stations:
        station = ttc.station_for(stop["name"])
        if not station:
            continue
        key = ttc.station_key(station["name"])
        for outage in alerts["outages"]:
            if outage["station_key"] == key and outage["kind"] == "elevator":
                found.append({
                    "id": f"elevator-{key}", "kind": "elevator", "severity": "blocker", "source": "ttc",
                    "label": f"Elevator out at {station['name']}: {outage['text']}"[:160],
                    "confirmable": False, "at_m": stop["at_m"], "lnglat": list(station["coordinates"]),
                })

    unique = {hazard["id"]: hazard for hazard in found}
    return sorted(({**h, "at_m": round(h["at_m"], 1)} for h in unique.values()), key=lambda h: h["at_m"])
