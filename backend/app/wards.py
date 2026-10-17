"""Ward report cards: City 311 accessibility reports per ward, plus live TTC, closure and forecast numbers.

Static numbers come from ml/09_export_wards.py (ward_stats.json, wards.geojson) and the
summaries from app.write_summaries (ward_summaries.json). Those files are re-read when they
change on disk, so new data needs no restart. Live numbers come from in-memory feeds
(feeds.py) and never wait on the network. Each carries `available`, so a feed that is down
shows as unavailable, never as zero.
"""

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from shapely.geometry import Point, shape
from shapely.prepared import PreparedGeometry, prep

from . import ai_summary, forecast, restrictions, risk, ttc

DATA = Path(__file__).parent / "data"
STATS_PATH, BOUNDARIES_PATH = DATA / "ward_stats.json", DATA / "wards.geojson"
TORONTO = ZoneInfo("America/Toronto")
SOURCES = {
    "311": "https://open.toronto.ca/dataset/311-service-requests-customer-initiated/",
    "wards": "https://open.toronto.ca/dataset/city-wards/",
    "ttc": "https://www.ttc.ca/service-advisories",
    "closures": restrictions.SOURCE_URL,
    "forecast": "https://open-meteo.com/",
}


@dataclass(frozen=True)
class Wards:
    stats: dict
    version: str                              # hash of ward_stats.json; changes with each export
    features: dict[int, dict]
    areas: dict[int, PreparedGeometry]
    stations: dict[int, list[str]]            # ward -> TTC station keys inside it
    summaries: dict[str, dict]


_loaded: tuple[tuple, Wards] | None = None
_load_lock = threading.Lock()
_cells: dict = {"features": None, "wards": None, "by_ward": {}}


def _signature() -> tuple:
    files = (STATS_PATH, BOUNDARIES_PATH, ai_summary.SUMMARIES_PATH)
    return tuple((str(path), path.stat().st_mtime_ns if path.exists() else 0) for path in files)


def _read() -> Wards:
    raw = STATS_PATH.read_bytes()
    features = {f["properties"]["id"]: f for f in json.loads(BOUNDARIES_PATH.read_text())["features"]}
    areas = {ward_id: prep(shape(f["geometry"])) for ward_id, f in features.items()}
    stations: dict[int, list[str]] = {ward_id: [] for ward_id in features}
    for key, station in ttc.stations().items():
        point = Point(station["coordinates"])
        ward_id = next((i for i, area in areas.items() if area.contains(point)), None)
        if ward_id is not None:
            stations[ward_id].append(key)
    return Wards(stats=json.loads(raw), version=hashlib.sha256(raw).hexdigest()[:12], features=features,
                 areas=areas, stations=stations, summaries=ai_summary.load_store()["wards"])


def load() -> Wards:
    """The ward data, re-read only when one of its files changes (one stat() per file per call)."""
    global _loaded
    signature = _signature()
    if _loaded is None or _loaded[0] != signature:
        with _load_lock:
            if _loaded is None or _loaded[0] != signature:
                _loaded = (signature, _read())
    return _loaded[1]


def list_wards() -> list[dict]:
    return [{"id": i, "name": f["properties"]["name"]} for i, f in load().features.items()]


def locate(lng: float, lat: float) -> dict:
    wards, point = load(), Point(lng, lat)
    for ward_id, area in wards.areas.items():
        if area.contains(point):
            return {"id": ward_id, "name": wards.features[ward_id]["properties"]["name"]}
    raise HTTPException(404, detail={"code": "outside_toronto", "message": "That place is not inside a Toronto ward."})


def static_facts(wards: Wards, ward_id: int) -> dict:
    """The numbers a summary is written from (see ai_summary.facts)."""
    ward = {**wards.stats["wards"][str(ward_id)], "name": wards.features[ward_id]["properties"]["name"],
            "station_count": len(wards.stations[ward_id])}
    return ai_summary.facts(ward)


def _elevators(keys: list[str]) -> dict:
    alerts = ttc.live_alerts()
    if not alerts["available"]:
        return {"available": False}
    all_stations = ttc.stations()
    out = [{"station": all_stations[o["station_key"]]["name"], "text": o["text"]}
           for o in alerts["outages"] if o["kind"] == "elevator" and o["station_key"] in keys]
    return {"available": True, "out": len(out), "outages": out, "stations": len(keys),
            "stations_with_elevator": sum(all_stations[key]["has_elevator"] for key in keys)}


def _closures(area: PreparedGeometry) -> dict:
    feed = restrictions.active()
    if not feed["available"]:
        return {"available": False}
    inside = [item for item in feed["items"] if area.intersects(item["geometry"])]
    return {"available": True, "count": len(inside), "sidewalk": sum(item["sidewalk"] for item in inside),
            "road_closed": sum(item["type"] == "ROAD_CLOSED" for item in inside)}


def _cells_by_ward(cells: list[dict], wards: Wards) -> dict[int, list[int]]:
    """Forecast cell indexes per ward (by cell centre), worked out once per forecast run."""
    if _cells["features"] is not cells or _cells["wards"] is not wards:
        by_ward: dict[int, list[int]] = {ward_id: [] for ward_id in wards.areas}
        for index, cell in enumerate(cells):
            centre = shape(cell["geometry"]).centroid
            ward_id = next((i for i, area in wards.areas.items() if area.contains(centre)), None)
            if ward_id is not None:
                by_ward[ward_id].append(index)
        _cells.update(features=cells, wards=wards, by_ward=by_ward)
    return _cells["by_ward"]


def _forecast(wards: Wards, ward_id: int) -> dict:
    try:
        prediction = forecast.predict()
    except HTTPException:
        return {"available": False}
    cells = prediction["features"]
    risks = [cells[i]["properties"]["risk"] for i in _cells_by_ward(cells, wards)[ward_id]]
    return {"available": True, "date": prediction["date"], "cells": len(risks),
            "high": sum(r >= risk.HIGH_RISK for r in risks), "elevated": sum(r >= risk.ELEVATED_RISK for r in risks)}


def _live_as_of() -> str:
    """When the oldest live feed shown on the card was fetched."""
    stamps = [feed.fetched_at for feed in (ttc.ALERTS, restrictions.FEED) if feed.fetched_at]
    moment = datetime.fromtimestamp(min(stamps), TORONTO) if stamps else datetime.now(TORONTO)
    return moment.isoformat(timespec="minutes")


def card(ward_id: int) -> dict:
    wards = load()
    if ward_id not in wards.features:
        raise HTTPException(404, detail={"code": "unknown_ward", "message": "Toronto has wards 1 to 25."})
    static = wards.stats["wards"].get(str(ward_id))
    if static is None:
        raise HTTPException(503, detail={"code": "ward_data_missing", "message": "Report data for this ward is not exported yet."})
    live = {"elevators": _elevators(wards.stations[ward_id]), "closures": _closures(wards.areas[ward_id]),
            "forecast": _forecast(wards, ward_id)}
    summary, source = ai_summary.summarize(static_facts(wards, ward_id), wards.summaries.get(str(ward_id)))
    return {
        **static, "name": wards.features[ward_id]["properties"]["name"],
        "geometry": wards.features[ward_id]["geometry"],
        "meta": wards.stats["meta"], "sources": SOURCES, "data_version": wards.version,
        "live_as_of": _live_as_of(), "live": live,
        "summary": summary, "summary_source": source,
        "summary_live": ai_summary.live_sentence(live, len(wards.stations[ward_id])),
    }
