"""Ward report cards: City 311 accessibility reports per ward, plus live TTC, closure and forecast numbers.

Static numbers come from ml/09_export_wards.py (ward_stats.json, wards.geojson). Each live
number carries `available`, so a feed that is down shows as unavailable, never as zero.
"""

import json
from datetime import datetime
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from shapely.geometry import Point, shape
from shapely.prepared import prep

from . import ai_summary, forecast, restrictions, risk, ttc

DATA = Path(__file__).parent / "data"
TORONTO = ZoneInfo("America/Toronto")
SOURCES = {
    "311": "https://open.toronto.ca/dataset/311-service-requests-customer-initiated/",
    "wards": "https://open.toronto.ca/dataset/city-wards/",
    "ttc": "https://www.ttc.ca/service-advisories",
    "closures": restrictions.SOURCE_URL,
    "forecast": "https://open-meteo.com/",
}


@cache
def _load():
    stats = json.loads((DATA / "ward_stats.json").read_text())
    features = json.loads((DATA / "wards.geojson").read_text())["features"]
    shapes = {f["properties"]["id"]: shape(f["geometry"]) for f in features}
    return stats, {f["properties"]["id"]: f for f in features}, shapes, {i: prep(s) for i, s in shapes.items()}


def list_wards() -> list[dict]:
    _, features, _, _ = _load()
    return [{"id": i, "name": f["properties"]["name"]} for i, f in features.items()]


def locate(lng: float, lat: float) -> dict:
    _, features, _, prepared = _load()
    point = Point(lng, lat)
    for ward_id, area in prepared.items():
        if area.contains(point):
            return {"id": ward_id, "name": features[ward_id]["properties"]["name"]}
    raise HTTPException(404, detail={"code": "outside_toronto", "message": "That place is not inside a Toronto ward."})


def _elevators(area) -> dict:
    try:
        stations = [s for s in ttc.station_status() if area.contains(Point(s["coordinates"]))]
        alerts_ok = ttc.live_alerts()["available"]
    except Exception:  # noqa: BLE001 - a broken feed must not break the card
        return {"available": False}
    out = [{"station": s["name"], "text": o["text"]} for s in stations for o in s["outages"] if o["kind"] == "elevator"]
    return {"available": alerts_ok, "out": len(out), "outages": out, "stations": len(stations),
            "stations_with_elevator": sum(s["has_elevator"] for s in stations)}


def _closures(area) -> dict:
    feed = restrictions.active()
    if not feed["available"]:
        return {"available": False}
    inside = [item for item in feed["items"] if area.intersects(item["geometry"])]
    return {"available": True, "count": len(inside), "sidewalk": sum(item["sidewalk"] for item in inside),
            "road_closed": sum(item["type"] == "ROAD_CLOSED" for item in inside)}


def _forecast(area) -> dict:
    try:
        prediction = forecast.predict()
    except HTTPException:
        return {"available": False}
    cells = [c for c in prediction["features"] if area.contains(shape(c["geometry"]).centroid)]
    return {"available": True, "date": prediction["date"], "cells": len(cells),
            "high": sum(c["properties"]["risk"] >= risk.HIGH_RISK for c in cells),
            "elevated": sum(c["properties"]["risk"] >= risk.ELEVATED_RISK for c in cells)}


def card(ward_id: int) -> dict:
    stats, features, _, prepared = _load()
    if ward_id not in features:
        raise HTTPException(404, detail={"code": "unknown_ward", "message": "Toronto has wards 1 to 25."})
    static = stats["wards"].get(str(ward_id))
    if static is None:
        raise HTTPException(503, detail={"code": "ward_data_missing", "message": "Report data for this ward is not exported yet."})
    area = prepared[ward_id]
    result = {
        **static, "name": features[ward_id]["properties"]["name"],
        "geometry": features[ward_id]["geometry"],
        "meta": stats["meta"], "sources": SOURCES,
        "generated_at": datetime.now(TORONTO).isoformat(timespec="minutes"),
        "live": {"elevators": _elevators(area), "closures": _closures(area), "forecast": _forecast(area)},
    }
    result["summary"], result["summary_source"] = ai_summary.summarize(result)
    return result
