"""TTC station accessibility (static) and live elevator, escalator and subway alerts."""

import json
import re
from datetime import datetime, timezone
from functools import cache
from pathlib import Path

import httpx

from .feeds import Feed

STATIONS_PATH = Path(__file__).parent / "data" / "ttc_stations.json"
ALERTS_URL = "https://alerts.ttc.ca/api/alerts/live-alerts"
ALERTS_TTL = 120
ALIASES = {"bloor": "bloor-yonge", "yonge": "bloor-yonge"}  # one interchange, two GTFS names


def station_key(name: str) -> str:
    """'Union Station - Northbound Platform Towards Finch', 'St. George' -> 'union', 'st george'."""
    base = re.split(r" - | Station\b", name)[0].strip().lower().replace(".", "")
    base = " ".join(base.split())
    return ALIASES.get(base, base)


@cache
def stations() -> dict[str, dict]:
    data = json.loads(STATIONS_PATH.read_text())
    return {station_key(station["name"]): station for station in data["stations"]}


def station_for(stop_name: str) -> dict | None:
    return stations().get(station_key(stop_name))


def _active(alert: dict, now: datetime) -> bool:
    period = alert.get("activePeriod") or {}
    try:
        start = datetime.fromisoformat(period.get("start", "").replace("Z", "+00:00"))
    except ValueError:
        return True
    end_text = period.get("end", "")
    end = None if not end_text or end_text.startswith("0001") else datetime.fromisoformat(end_text.replace("Z", "+00:00"))
    return start <= now and (end is None or now <= end)


def parse_alerts(data: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    outages = []
    for alert in data.get("accessibility") or []:
        kind = (alert.get("routeType") or "").lower()
        text = alert.get("headerText") or alert.get("title") or ""
        if kind not in ("elevator", "escalator") or ":" not in text or not _active(alert, now):
            continue
        station = text.split(":", 1)[0].strip()
        outages.append({"station": station, "station_key": station_key(station), "kind": kind,
                        "code": alert.get("elevatorCode") or alert.get("escalatorCode"),
                        "text": text.split(":", 1)[1].strip(),
                        "since": (alert.get("activePeriod") or {}).get("start")})
    closures = []
    for alert in data.get("routes") or []:
        if (alert.get("routeType") != "Subway" or alert.get("effect") not in ("NO_SERVICE", "REDUCED_SERVICE")
                or not alert.get("stopStart") or not _active(alert, now)):
            continue
        closures.append({"line": alert.get("route"), "from_station": alert["stopStart"], "to_station": alert.get("stopEnd"),
                         "stations": {station_key(alert["stopStart"]), station_key(alert.get("stopEnd") or "")},
                         "text": alert.get("customHeaderText") or alert.get("title") or ""})
    return {"updated": data.get("lastUpdated"), "outages": outages, "closures": closures, "available": True}


def _fetch_alerts() -> dict:
    response = httpx.get(ALERTS_URL, headers={"User-Agent": "ClearPath-Toronto/0.1"}, timeout=8)
    response.raise_for_status()
    return parse_alerts(response.json())


ALERTS = Feed("ttc-alerts", _fetch_alerts, ALERTS_TTL)


def live_alerts() -> dict:
    """Current outages and closures. Returns available=False when the feed has not loaded."""
    return ALERTS.get() or {"updated": None, "outages": [], "closures": [], "available": False}


def station_status() -> list[dict]:
    """Every station with its elevator access and current outages, for the map layer."""
    alerts = live_alerts()
    result = []
    for key, station in stations().items():
        outages = [{k: outage[k] for k in ("kind", "code", "text", "since")}
                   for outage in alerts["outages"] if outage["station_key"] == key]
        result.append({**station, "outages": outages})
    return result
