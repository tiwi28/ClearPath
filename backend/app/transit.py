"""TTC trip options from Transitous, checked against TTC station elevators and live outages.

Transitous (MOTIS) marks trips through stations without elevators as accessible, so every
rapid-transit stop is checked here against ttc_stations.json and the live alerts feed.
"""

import httpx

from . import risk, ttc
from .profiles import Profile

TRANSITOUS_URL = "https://api.transitous.org/api/v5/plan"
USER_AGENT = "ClearPath-Toronto/0.1 (accessible trip planner; hackathon project)"
RAPID_MODES = {"SUBWAY", "TRAM", "METRO", "RAIL", "REGIONAL_RAIL", "LIGHT_RAIL"}
SURFACE_MODES = "BUS,TRAM"  # TTC buses and streetcars are all low-floor with ramps
MAX_OPTIONS = 3


class TransitUnavailable(Exception):
    pass


def decode(points: str, precision: int = 6) -> list[list[float]]:
    """Decode a Google encoded polyline into [lng, lat] pairs."""
    coordinates, index, lat, lng, factor = [], 0, 0, 0, 10 ** precision
    while index < len(points):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                byte = ord(points[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lng += deltas[1]
        coordinates.append([lng / factor, lat / factor])
    return coordinates


def request(profile: Profile, from_, to, transit_modes: str | None = None) -> dict:
    params = {"fromPlace": f"{from_[1]},{from_[0]}", "toPlace": f"{to[1]},{to[0]}",
              "numItineraries": 5, **profile.transit}
    if transit_modes:
        params["transitModes"] = transit_modes
    try:
        response = httpx.get(TRANSITOUS_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=15)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise TransitUnavailable(str(error)) from None


def station_issues(stop_name: str, profile: Profile, alerts: dict) -> list[dict]:
    station = ttc.station_for(stop_name)
    if not station:
        return []
    blocker = "blocker" if profile.step_free_stations else "warning"
    issues = []
    if not station["has_elevator"]:
        issues.append({"severity": blocker, "station": station["name"], "kind": "no_elevator",
                       "text": f"{station['name']} has no elevator"})
    for outage in alerts["outages"]:
        if outage["station_key"] != ttc.station_key(station["name"]):
            continue
        if outage["kind"] == "elevator":
            issues.append({"severity": blocker, "station": station["name"], "kind": "elevator_out",
                           "text": f"Elevator out at {station['name']}: {outage['text']}"})
        elif not profile.step_free_stations:  # escalators matter to people who can't use stairs but can stand
            issues.append({"severity": "warning", "station": station["name"], "kind": "escalator_out",
                           "text": f"Escalator out at {station['name']}: {outage['text']}"})
    return issues


def normalize(itinerary: dict, profile: Profile, alerts: dict, cells: list[dict]) -> dict:
    legs, issues = [], []
    for leg in itinerary["legs"]:
        geometry = leg.get("legGeometry") or {}
        coordinates = decode(geometry.get("points", ""), geometry.get("precision", 6)) if geometry.get("points") else []
        item = {
            "mode": leg["mode"], "line": leg.get("routeShortName"), "headsign": leg.get("headsign"),
            "color": f"#{leg['routeColor']}" if leg.get("routeColor") else None,
            "from_name": leg["from"]["name"], "to_name": leg["to"]["name"],
            "start": leg["startTime"], "end": leg["endTime"], "duration_s": leg.get("duration", 0),
            "distance_m": leg.get("distance") or 0,
            "geometry": {"type": "LineString", "coordinates": coordinates} if len(coordinates) >= 2 else None,
            "risk": risk.score_path(cells, coordinates) if cells and leg["mode"] == "WALK" and len(coordinates) >= 2 else None,
        }
        if leg["mode"] in RAPID_MODES:
            for name in (leg["from"]["name"], leg["to"]["name"]):
                issues += station_issues(name, profile, alerts)
            stops = {ttc.station_key(leg["from"]["name"]), ttc.station_key(leg["to"]["name"])}
            stops |= {ttc.station_key(stop["name"]) for stop in leg.get("intermediateStops") or []}
            for closure in alerts["closures"]:
                if closure["line"] == leg.get("routeShortName") and closure["stations"] & stops:
                    issues.append({"severity": "warning", "station": closure["from_station"], "kind": "service_change",
                                   "text": f"Line {closure['line']} notice: {closure['text']}"})
        legs.append(item)
    unique = list({issue["text"]: issue for issue in issues}.values())
    return {
        "start": itinerary["startTime"], "end": itinerary["endTime"], "duration_s": itinerary["duration"],
        "transfers": itinerary.get("transfers", 0),
        "walk_m": round(sum(leg["distance_m"] for leg in legs if leg["mode"] == "WALK")),
        "legs": legs, "issues": unique, "step_free": not any(issue["severity"] == "blocker" for issue in unique),
    }


def signature(option: dict) -> tuple:
    return tuple((leg["mode"], leg["line"], leg["from_name"], leg["to_name"]) for leg in option["legs"])


def plan(profile: Profile, from_, to, cells: list[dict]) -> tuple[list[dict], list[str]]:
    """Up to MAX_OPTIONS transit options plus notes about trips that were hidden."""
    alerts = ttc.live_alerts()
    notes = [] if alerts["available"] else ["TTC elevator alerts are unavailable; outages may not be shown."]
    options = [normalize(itinerary, profile, alerts, cells) for itinerary in request(profile, from_, to)["itineraries"]]
    if profile.step_free_stations:
        blocked = [option for option in options if not option["step_free"]]
        options = [option for option in options if option["step_free"]]
        if blocked:
            stations = sorted({issue["station"] for option in blocked for issue in option["issues"] if issue["severity"] == "blocker"})
            notes.append(f"Hid {len(blocked)} trip{'s' if len(blocked) > 1 else ''} through stations without a working elevator ({', '.join(stations)}).")
        if not options:
            # Every subway option failed the elevator check: buses and streetcars are all ramp-equipped.
            surface = request(profile, from_, to, SURFACE_MODES)["itineraries"]
            options = [option for option in (normalize(it, profile, alerts, cells) for it in surface) if option["step_free"]]
    seen, result = set(), []
    for option in sorted(options, key=lambda option: option["end"]):
        if signature(option) not in seen:
            seen.add(signature(option))
            result.append(option)
    return result[:MAX_OPTIONS], notes
