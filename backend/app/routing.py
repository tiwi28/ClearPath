"""Trip planning: the typical walking route, the profile's accessible route, and TTC options.

ORS is called at the provider boundary and its GeoJSON is normalized here.
"""

import json
import math
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from shapely.geometry import LineString, MultiPolygon, Point, mapping, shape
from shapely.ops import substring, unary_union

from . import barriers, forecast, risk, transit
from .config import settings
from .profiles import PROFILES, Profile
from .schemas import NonNegative, PlanRequest, RouteGeometry, Step

ORS_URL = "https://api.openrouteservice.org/v2/directions/{profile}/geojson"
STEPS_WAYTYPE = 8          # ORS extra_info "waytype" value for stairs
RECOVERY_M = (40, 120, 300)  # how far in from an endpoint to look for a reachable street
MAX_DETOUR = 1.5           # a lower-risk route may be at most this much longer than the standard one
MIN_GAIN = 0.03            # ...and must lower the length-weighted mean risk by at least this much
CACHE_TTL = 300
_cache: dict[str, tuple[float, dict]] = {}


def require_key():
    if not settings.ors_api_key.strip():
        raise HTTPException(503, detail={
            "code": "routing_not_configured", "message": "Live routing is not configured. Add the ORS API key to the backend.",
        })


def geocode(text: str) -> list[dict]:
    """Address suggestions within Toronto, as {label, coordinates: [lng, lat]}."""
    require_key()
    west, south, east, north = barriers.TORONTO_BBOX
    try:
        response = httpx.get(
            "https://api.openrouteservice.org/geocode/autocomplete",
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


def ors(profile: str, coordinates, options: dict | None = None, preference: str = "recommended",
        extra_info: list[str] | None = None) -> dict:
    require_key()
    body = {"coordinates": [list(point) for point in coordinates], "instructions": True,
            "instructions_format": "text", "language": "en", "preference": preference}
    if options:
        body["options"] = options
    if extra_info:
        body["extra_info"] = extra_info
    key = profile + json.dumps(body, sort_keys=True)
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return dict(cached[1])
    try:
        response = httpx.post(ORS_URL.format(profile=profile), headers={"Authorization": settings.ors_api_key},
                              json=body, timeout=20)
    except httpx.TimeoutException:
        raise HTTPException(504, detail={"code": "routing_timeout", "message": "Routing timed out. Try again."}) from None
    except httpx.RequestError:
        raise HTTPException(502, detail={"code": "routing_unavailable", "message": "The routing service is unavailable. Try again."}) from None

    try:
        data = response.json()
        error = data.get("error", {})
        if not response.is_success:
            if response.status_code in (403, 429):
                raise HTTPException(503, detail={"code": "routing_quota", "message": "The routing service's daily limit has been reached. Try again later, or use a different ORS API key."})
            if response.status_code == 404 or (isinstance(error, dict) and error.get("code") in (2009, 2010)):
                raise HTTPException(404, detail={"code": "no_route", "message": "No route found with these accessibility constraints. Try other points."})
            raise HTTPException(502, detail={"code": "routing_unavailable", "message": "The routing service could not calculate this trip. Try again."})
        feature = data["features"][0]
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
    _cache[key] = (time.time(), result)
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
    step-free route exists, and report the remaining stretch as unverified."""
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
            warnings.append(f"We couldn't confirm a step-free path for the last {round(gap['length_m'])} m near {place}"
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
        warnings.append("No step-free street route was found for this trip." if error.status_code == 404
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
    if risk_info["available"]:
        warnings.append("Predicted risk estimates likely 311 reports; it is not a confirmed barrier.")
    warnings.append("Barrier coverage is incomplete; a calculated route is not a guarantee of accessibility.")
    if settings.barrier_source == "fixtures":
        warnings.append("Known-barrier locations are fictional sample data, not current Toronto conditions.")
    return {"profile": request.profile, "ideal": ideal, "accessible": accessible, "transit": options,
            "risk": risk_info, "warnings": warnings, "barrier_source": settings.barrier_source}
