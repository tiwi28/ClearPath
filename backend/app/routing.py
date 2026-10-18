"""Trip planning: the typical walking route, the profile's accessible route, and TTC options.

ORS is called at the provider boundary and its GeoJSON is normalized here.
"""

import json
import logging
import math
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from shapely.geometry import LineString, MultiPolygon, Point, mapping, shape
from shapely.ops import substring, unary_union

from . import barriers, forecast, risk, transit
from .config import settings
from .profiles import PROFILES, Profile
from .schemas import NonNegative, PlanRequest, RouteGeometry, Step

# Directions use settings.ors_base_url (public api.heigit.org by default, or a local server).
# Address search always uses the public geocoder; a local ORS has none.
GEOCODE_URL = "https://api.heigit.org/pelias/v1/autocomplete"
PUBLIC_ORS_HOSTS = ("api.heigit.org", "api.openrouteservice.org")  # need an API key; a local server doesn't
ORS_TIMEOUT = 12
RETRY_STATUSES = (502, 503, 504)
DOWN_FOR = 300             # once a profile fails, skip straight to the fallback for this long
STEPS_WAYTYPE = 8          # ORS extra_info "waytype" value for stairs
RECOVERY_M = (40, 120, 300)  # how far in from an endpoint to look for a reachable street
MAX_DETOUR = 1.5           # a lower-risk route may be at most this much longer than the standard one
MIN_GAIN = 0.03            # ...and must lower the length-weighted mean risk by at least this much
CACHE_TTL = 300
CACHE_SIZE = 256           # most recent ORS answers kept; oldest dropped first
FALLBACK_FOR = ("foot-walking", "wheelchair")
FALLBACK_WARNING = ("Accessible routing is temporarily unavailable, so this route uses a backup network. "
                    "It avoids stairs, but kerbs and slopes aren't checked.")
IDEAL_FALLBACK_NOTE = "The typical walking route was calculated on a backup network while walking routing is down."
log = logging.getLogger(__name__)
_cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
_cache_lock = threading.Lock()
_down: dict[str, float] = {}  # ORS profile -> when it last timed out or errored


def _cached(key: str) -> dict | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.time() - entry[0] < CACHE_TTL:
            _cache.move_to_end(key)
            return dict(entry[1])
        _cache.pop(key, None)
        return None


def _remember(key: str, result: dict) -> None:
    with _cache_lock:
        _cache[key] = (time.time(), result)
        _cache.move_to_end(key)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)


def require_key(url: str):
    if urlparse(url).hostname in PUBLIC_ORS_HOSTS and not settings.ors_api_key.strip():
        raise HTTPException(503, detail={
            "code": "routing_not_configured", "message": "Live routing is not configured. Add the ORS API key to the backend.",
        })


def geocode(text: str) -> list[dict]:
    """Address suggestions within Toronto, as {label, coordinates: [lng, lat]}."""
    require_key(GEOCODE_URL)
    west, south, east, north = barriers.TORONTO_BBOX
    try:
        response = httpx.get(
            GEOCODE_URL,
            headers={"Authorization": settings.ors_api_key},
            params={"text": text, "boundary.rect.min_lon": west, "boundary.rect.min_lat": south,
                    "boundary.rect.max_lon": east, "boundary.rect.max_lat": north,
                    "focus.point.lon": -79.383, "focus.point.lat": 43.653, "size": 6},
            timeout=10,
        )
        response.raise_for_status()
        return [{"label": feature["properties"]["label"], "coordinates": feature["geometry"]["coordinates"][:2]}
                for feature in response.json()["features"]]
    except httpx.TimeoutException:
        raise HTTPException(504, detail={"code": "geocoding_timeout", "message": "Address search timed out. Try again."}) from None
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(502, detail={"code": "geocoding_unavailable", "message": "Address search is unavailable. Click the map instead."}) from None


def with_constraints(options: dict, constraints: list[dict]) -> dict:
    if not constraints:
        return options
    area = unary_union([shape(feature["geometry"]) for feature in constraints])
    if area.geom_type == "Polygon":
        area = MultiPolygon([area])
    return {**options, "avoid_polygons": mapping(area)}


def _is_down(profile: str) -> bool:
    with _cache_lock:
        return time.time() - _down.get(profile, 0) < DOWN_FOR


def _mark_down(profile: str) -> None:
    with _cache_lock:
        _down[profile] = time.time()


def _fallback_options(options: dict | None) -> dict | None:
    """Wheelchair-only settings (slope and kerb limits) are rejected by other profiles; avoiding stairs still applies."""
    if options and "profile_params" in options:
        return {key: value for key, value in options.items() if key != "profile_params"}
    return options


def ors(profile: str, coordinates, options: dict | None = None, preference: str = "recommended",
        extra_info: list[str] | None = None) -> dict:
    """Route on `profile`. If walking or wheelchair routing is down, route on ORS_FALLBACK_PROFILE
    instead and mark the result with "fallback": True so the plan can say so."""
    fallback = settings.ors_fallback_profile.strip()
    if not fallback or profile not in FALLBACK_FOR or fallback == profile:
        return _directions(profile, coordinates, options, preference, extra_info, attempts=2)
    if not (settings.ors_force_fallback or _is_down(profile)):
        try:
            return _directions(profile, coordinates, options, preference, extra_info, attempts=1)
        except HTTPException as error:
            if error.detail.get("code") not in ("routing_timeout", "routing_unavailable"):
                raise
            log.warning("ORS %s is failing (%s); using %s for %ss", profile, error.detail["code"], fallback, DOWN_FOR)
            _mark_down(profile)
    result = _directions(fallback, coordinates, _fallback_options(options), preference, extra_info, attempts=2)
    return {**result, "fallback": True}


def _directions(profile: str, coordinates, options: dict | None, preference: str,
                extra_info: list[str] | None, attempts: int) -> dict:
    url = f"{settings.ors_base_url.rstrip('/')}/directions/{profile}/geojson"
    require_key(url)
    body = {"coordinates": [list(point) for point in coordinates], "instructions": True,
            "instructions_format": "text", "language": "en", "preference": preference}
    if options:
        body["options"] = options
    if extra_info:
        body["extra_info"] = extra_info
    key = url + json.dumps(body, sort_keys=True)
    cached = _cached(key)
    if cached:
        return cached
    headers = {"Authorization": settings.ors_api_key} if settings.ors_api_key.strip() else {}
    for attempt in range(1, attempts + 1):
        # Public ORS sometimes drops a request or answers with a gateway error page; one retry usually works.
        try:
            response = httpx.post(url, headers=headers, json=body, timeout=ORS_TIMEOUT)
        except httpx.TimeoutException:
            if attempt == attempts:
                raise HTTPException(504, detail={"code": "routing_timeout", "message": "Routing timed out. Try again."}) from None
            continue
        except httpx.RequestError:
            if attempt == attempts:
                raise HTTPException(502, detail={"code": "routing_unavailable", "message": "The routing service is unavailable. Try again."}) from None
            continue
        if response.status_code not in RETRY_STATUSES or attempt == attempts:
            break

    if not response.is_success:
        try:
            error = response.json().get("error", {})
        except (ValueError, AttributeError):
            error = {}  # gateway error pages are HTML
        code = error.get("code") if isinstance(error, dict) else None
        if response.status_code in (403, 429):
            raise HTTPException(503, detail={"code": "routing_quota", "message": "The routing service's daily limit has been reached. Try again later, or use a different ORS API key."})
        if response.status_code == 404 or code in (2009, 2010):
            raise HTTPException(404, detail={"code": "no_route", "message": "No route found with these accessibility constraints. Try other points."})
        if response.status_code == 400:
            log.warning("ORS rejected the %s request: %s", profile, error)
        raise HTTPException(502, detail={"code": "routing_unavailable", "message": "The routing service could not calculate this trip. Try again."})
    try:
        feature = response.json()["features"][0]
        geometry = RouteGeometry.model_validate(feature["geometry"])
        summary = feature["properties"]["summary"]
        number = TypeAdapter(NonNegative)
        result = {
            "geometry": geometry.model_dump(mode="json"),
            "distance_m": number.validate_python(summary.get("distance", 0)),
            "duration_s": number.validate_python(summary.get("duration", 0)),
            "steps": [Step(instruction=step["instruction"], distance_m=step["distance"],
                           way_points=step.get("way_points"), type=step.get("type")).model_dump()
                      for segment in feature["properties"]["segments"] for step in segment["steps"]],
            "waytypes": feature["properties"].get("extras", {}).get("waytype", {}).get("values", []),
        }
    except (ValueError, KeyError, IndexError, TypeError, AttributeError, ValidationError):
        raise HTTPException(502, detail={"code": "invalid_routing_response", "message": "The routing service returned an invalid route. Try again."}) from None
    _remember(key, result)
    return dict(result)


def stairs(result: dict) -> list[dict]:
    coordinates = result["geometry"]["coordinates"]
    return [{"type": "LineString", "coordinates": coordinates[start:end + 1]}
            for start, end, value in result.pop("waytypes", []) if value == STEPS_WAYTYPE and end > start]


# --- Metric helpers: ORS coordinates are lng/lat; distances along a path need metres. ---

def _scale(coordinates) -> tuple[float, float]:
    return 111_320 * math.cos(math.radians(coordinates[0][1])), 110_540


def _metric(coordinates) -> LineString:
    kx, ky = _scale(coordinates)
    return LineString([(x * kx, y * ky) for x, y in coordinates])


def _degrees(points, coordinates) -> list[list[float]]:
    kx, ky = _scale(coordinates)
    return [[round(x / kx, 7), round(y / ky, 7)] for x, y in points]


def _piece(coordinates, start_m: float, end_m: float) -> dict:
    part = substring(_metric(coordinates), start_m, end_m)
    return {"type": "LineString", "coordinates": _degrees(part.coords, coordinates)}


def recover(profile: Profile, request: PlanRequest, ideal: dict, options: dict) -> dict | None:
    """The profile's routing failed, usually because an endpoint snapped onto a path that only
    connects by stairs (PATH, plazas, park paths). Walk in along the typical route until a
    route without stairs exists, and report the remaining stretch as unverified."""
    coordinates = ideal["geometry"]["coordinates"]
    line = _metric(coordinates)
    total = line.length
    stair_starts = [line.project(Point(_metric(segment["coordinates"]).coords[0])) for segment in ideal["stairs"]]
    attempts = [(0, m) for m in RECOVERY_M] + [(m, 0) for m in RECOVERY_M] + [(m, m) for m in RECOVERY_M]
    for start_m, end_m in attempts:
        if start_m + end_m >= total * 0.8:
            continue
        start = list(request.from_) if not start_m else _degrees([line.interpolate(start_m).coords[0]], coordinates)[0]
        end = list(request.to) if not end_m else _degrees([line.interpolate(total - end_m).coords[0]], coordinates)[0]
        try:
            result = ors(profile.ors_profile, [start, end], options, profile.ors_preference)
        except HTTPException as error:
            if error.status_code == 404:
                continue
            raise
        gaps = []
        if start_m:
            gaps.append({"end": "start", "geometry": _piece(coordinates, 0, start_m), "length_m": start_m,
                         "uses_stairs": any(at <= start_m for at in stair_starts)})
        if end_m:
            gaps.append({"end": "destination", "geometry": _piece(coordinates, total - end_m, total), "length_m": end_m,
                         "uses_stairs": any(at >= total - end_m for at in stair_starts)})
        return {**result, "unverified": gaps}
    return None


def crosses_obstruction(result: dict, constraints: list[dict]) -> bool:
    # A detour can leave the original search area. Check the actual returned path.
    final_constraints = barriers.blockers(barriers.query_features(barriers.route_bounds(result["geometry"]["coordinates"])))
    path = shape(result["geometry"])
    return any(path.intersects(shape(feature["geometry"])) for feature in constraints + final_constraints)


def lower_risk_route(profile: Profile, request: PlanRequest, constraints: list[dict], cells: list[dict], standard: dict) -> dict | None:
    """Avoid progressively fewer of the riskiest nearby cells until ORS finds a worthwhile detour."""
    endpoints = [request.from_, request.to]
    candidates = risk.avoid_candidates(cells, barriers.route_bounds(standard["geometry"]["coordinates"] + endpoints), endpoints)
    for cutoff in risk.cutoffs(candidates):
        avoid = constraints + [cell for cell in candidates if cell["properties"]["risk"] >= cutoff]
        try:
            candidate = ors(profile.ors_profile, endpoints, with_constraints(profile.ors_options, avoid), profile.ors_preference)
        except HTTPException as error:
            if error.status_code in (404, 502):  # too many areas avoided, or polygons ORS rejects
                continue
            raise
        candidate.pop("waytypes", None)
        candidate["risk"] = risk.score_path(cells, candidate["geometry"]["coordinates"])
        if (candidate["distance_m"] <= standard["distance_m"] * MAX_DETOUR
                and candidate["risk"]["mean"] <= standard["risk"]["mean"] - MIN_GAIN
                and not crosses_obstruction(candidate, constraints)):
            return candidate
    return None


def finish(profile: Profile, result: dict) -> dict:
    result.pop("waytypes", None)
    if profile.speed_mps:
        result["duration_s"] = round(result["distance_m"] / profile.speed_mps)
    return result


def accessible_route(profile: Profile, request: PlanRequest, ideal: dict | None, cells: list[dict],
                     constraints: list[dict], warnings: list[str]) -> dict:
    options = with_constraints(profile.ors_options, constraints)
    try:
        result = ors(profile.ors_profile, [request.from_, request.to], options, profile.ors_preference)
        result["unverified"] = []
    except HTTPException as error:
        if error.status_code != 404 or not ideal:
            raise
        result = recover(profile, request, ideal, options)
        if not result:
            raise
        for gap in result["unverified"]:
            place = "your destination" if gap["end"] == "destination" else "your start"
            warnings.append(f"We couldn't confirm a path without stairs for the last {round(gap['length_m'])} m near {place}"
                            + (" (the usual way in uses stairs)." if gap["uses_stairs"] else ". Check entrances before you go."))
    if crosses_obstruction(result, constraints):
        raise HTTPException(409, detail={
            "code": "blocked_route", "message": "The calculated path still crosses a known obstruction. Try different points.",
        })
    result["risk"] = risk.score_path(cells, result["geometry"]["coordinates"]) if cells else None
    result = finish(profile, result)
    standard = None
    if request.avoid_risk and cells and not result["unverified"]:
        # Predicted risk is a preference, not an obstruction: keep the standard route unless a detour clearly helps.
        safer = lower_risk_route(profile, request, constraints, cells, result)
        if safer:
            standard = {key: result[key] for key in ("geometry", "distance_m", "duration_s", "steps", "risk")}
            result = {**finish(profile, safer), "unverified": []}
        elif not risk.avoid_candidates(cells, barriers.route_bounds(result["geometry"]["coordinates"]), [request.from_, request.to]):
            warnings.append("Predicted barrier risk is low along this trip.")
    return {**result, "risk_avoided": standard is not None, "standard": standard,
            "avoided_barrier_ids": [feature["properties"]["id"] for feature in constraints]}


def plan(request: PlanRequest) -> dict:
    profile = PROFILES[request.profile]
    warnings: list[str] = []
    try:
        forecast_map = forecast.predict(request.day)
        cells = forecast_map["features"]
        risk_info = {"available": True, "date": forecast_map["date"], "reports_through": forecast_map["reports_through"]}
        warnings += forecast_map["warnings"]
    except HTTPException as error:
        if error.status_code == 422:
            raise
        cells, risk_info = [], {"available": False, "date": None, "reports_through": None}
        warnings.append(error.detail["message"] if isinstance(error.detail, dict) else str(error.detail))

    endpoints = [request.from_, request.to]
    # Transit planning is independent of street routing, so it runs while ORS works.
    pool = ThreadPoolExecutor(max_workers=1)
    pending_transit = pool.submit(transit.plan, profile, request.from_, request.to, cells) if request.include_transit else None
    pool.shutdown(wait=False)
    constraints = barriers.blockers(barriers.query_features(barriers.route_bounds(endpoints)))
    try:
        ideal = ors("foot-walking", endpoints, extra_info=["waytype"])
        ideal["stairs"] = stairs(ideal)
        ideal["risk"] = risk.score_path(cells, ideal["geometry"]["coordinates"]) if cells else None
    except HTTPException as error:
        if error.status_code != 404:
            raise
        ideal = None

    accessible, failure = None, None
    try:
        accessible = accessible_route(profile, request, ideal, cells, constraints, warnings)
    except HTTPException as error:
        if error.status_code not in (404, 409):
            raise
        failure = error
        warnings.append("No street route without stairs was found for this trip." if error.status_code == 404
                        else error.detail["message"])

    options = []
    if pending_transit:
        try:
            options, notes = pending_transit.result()
            warnings += notes
        except transit.TransitUnavailable:
            warnings.append("TTC trip planning is unavailable right now; showing street routes only.")

    if not accessible and not options:
        if failure and failure.status_code == 409:
            raise failure
        raise HTTPException(404, detail={"code": "no_route", "message": "No accessible way to make this trip was found. Try points on a nearby street."})
    if accessible and accessible.get("fallback"):
        warnings.insert(0, FALLBACK_WARNING)
    elif ideal and ideal.get("fallback"):
        warnings.insert(0, IDEAL_FALLBACK_NOTE)
    if risk_info["available"]:
        warnings.append("Predicted risk estimates likely 311 reports; it is not a confirmed barrier.")
    warnings.append("Barrier coverage is incomplete; a calculated route is not a guarantee of accessibility.")
    if settings.barrier_source == "fixtures":
        warnings.append("Known-barrier locations are fictional sample data, not current Toronto conditions.")
    return {"profile": request.profile, "ideal": ideal, "accessible": accessible, "transit": options,
            "risk": risk_info, "warnings": warnings, "barrier_source": settings.barrier_source}
