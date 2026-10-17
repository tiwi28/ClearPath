import json

import httpx
import psycopg
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import barriers, forecast, routing
from app.config import settings
from app.main import app
from conftest import ors_route

client = TestClient(app)
TRIP = {"from": [-79.3832, 43.6534], "to": [-79.3802, 43.6561], "include_transit": False}
DIRECT = [TRIP["from"], TRIP["to"]]
AROUND = [TRIP["from"], [-79.3832, 43.6561], TRIP["to"]]


def provider(monkeypatch, handler):
    """handler(profile, body) -> (status, json). Records every ORS call."""
    calls = []

    def post(url, **kwargs):
        profile = url.split("/directions/")[1].split("/")[0]
        calls.append({"url": url, "profile": profile, **kwargs})
        status, body = handler(profile, kwargs["json"])
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    return calls


def ok(profile, body):
    return 200, ors_route(body["coordinates"])


def polygon_count(call):
    return len(call["json"].get("options", {}).get("avoid_polygons", {}).get("coordinates", []))


def use_polygon(monkeypatch, tmp_path, *, verification="verified", coordinates=None):
    coordinates = coordinates or [[-79.38185, 43.6545], [-79.3812, 43.6545], [-79.3812, 43.6551], [-79.38185, 43.6551], [-79.38185, 43.6545]]
    path = tmp_path / "barriers.json"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [{
        "type": "Feature", "geometry": {"type": "Polygon", "coordinates": [coordinates]},
        "properties": {"id": 55, "source": "311", "kind": "closure", "status": "open",
                       "verification": verification, "blocks_route": True},
    }]}))
    monkeypatch.setattr(barriers, "FIXTURE_PATH", path)


def test_plan_returns_typical_and_accessible_routes(monkeypatch):
    calls = provider(monkeypatch, ok)
    response = client.post("/plan", json={**TRIP, "avoid_risk": False})
    assert response.status_code == 200
    body = response.json()
    assert body["profile"] == "manual_wheelchair"
    assert body["ideal"]["distance_m"] == 920
    assert body["accessible"]["avoided_barrier_ids"] == [2]
    assert body["risk"] == {"available": True, "date": "2026-10-17", "reports_through": "2026-09-30"}
    assert [call["profile"] for call in calls] == ["foot-walking", "wheelchair"]
    assert calls[0]["json"]["extra_info"] == ["waytype"]
    wheelchair = calls[1]["json"]["options"]
    assert wheelchair["avoid_features"] == ["steps"]
    assert wheelchair["profile_params"]["restrictions"]["maximum_incline"] == 6
    assert wheelchair["avoid_polygons"]["type"] == "MultiPolygon"
    assert calls[1]["headers"]["Authorization"] == "test-key"


def test_typical_route_reports_stairs(monkeypatch):
    coordinates = [TRIP["from"], [-79.382, 43.654], [-79.381, 43.655], TRIP["to"]]
    provider(monkeypatch, lambda profile, body: (200, ors_route(coordinates, waytypes=[[0, 1, 3], [1, 2, 8], [2, 3, 7]])))
    stairs = client.post("/plan", json=TRIP).json()["ideal"]["stairs"]
    assert stairs == [{"type": "LineString", "coordinates": [[-79.382, 43.654], [-79.381, 43.655]]}]


@pytest.mark.parametrize("profile,ors_profile,seconds", [
    ("power_wheelchair", "wheelchair", 810), ("walker", "foot-walking", 1022), ("limited_stamina", "foot-walking", 1150),
])
def test_profiles_choose_routing_settings_and_pace(monkeypatch, profile, ors_profile, seconds):
    calls = provider(monkeypatch, ok)
    body = client.post("/plan", json={**TRIP, "profile": profile, "avoid_risk": False}).json()
    assert calls[1]["profile"] == ors_profile
    assert calls[1]["json"]["options"]["avoid_features"] == ["steps"]
    assert body["accessible"]["duration_s"] == seconds
    if profile == "limited_stamina":
        assert calls[1]["json"]["preference"] == "shortest"


def test_island_endpoint_is_recovered_with_an_unverified_gap(monkeypatch):
    """Wheelchair routing fails until the destination moves onto the street network."""
    def handler(profile, body):
        if profile == "wheelchair" and body["coordinates"][-1] == TRIP["to"]:
            return 404, {"error": {"code": 2009, "message": "Route could not be found"}}
        return ok(profile, body)
    provider(monkeypatch, handler)
    body = client.post("/plan", json={**TRIP, "avoid_risk": False}).json()
    gaps = body["accessible"]["unverified"]
    assert [(gap["end"], gap["length_m"]) for gap in gaps] == [("destination", 40)]
    assert gaps[0]["geometry"]["coordinates"][-1] == pytest.approx(TRIP["to"], abs=1e-6)
    assert any("last 40 m near your destination" in warning for warning in body["warnings"])


def test_no_route_anywhere_is_404(monkeypatch):
    provider(monkeypatch, lambda profile, body: (404, {"error": {"code": 2009}}))
    response = client.post("/plan", json=TRIP)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "no_route"


def test_lower_risk_detour_keeps_the_standard_route_for_comparison(monkeypatch):
    def handler(profile, body):
        detour = profile == "wheelchair" and polygon_count({"json": body}) > 1
        return 200, ors_route(AROUND if detour else body["coordinates"])
    calls = provider(monkeypatch, handler)
    accessible = client.post("/plan", json=TRIP).json()["accessible"]
    assert accessible["risk_avoided"] is True
    assert len(accessible["geometry"]["coordinates"]) == 3
    assert accessible["standard"]["geometry"]["coordinates"] == DIRECT
    assert accessible["risk"]["mean"] < accessible["standard"]["risk"]["mean"]
    # Only the mid-route cell is avoided: the start cell is high risk but holds an endpoint.
    assert polygon_count(calls[2]) == polygon_count(calls[1]) + 1


def test_lower_risk_route_needs_a_meaningful_gain(monkeypatch):
    calls = provider(monkeypatch, ok)
    accessible = client.post("/plan", json=TRIP).json()["accessible"]
    assert accessible["risk_avoided"] is False
    assert accessible["standard"] is None
    assert len(calls) == 3


def test_plan_still_routes_when_the_forecast_is_unavailable(monkeypatch):
    def unavailable(day=None):
        raise HTTPException(503, detail={"code": "risk_unavailable", "message": "The weather forecast is unavailable."})
    monkeypatch.setattr(forecast, "predict", unavailable)
    calls = provider(monkeypatch, ok)
    body = client.post("/plan", json=TRIP).json()
    assert body["risk"]["available"] is False
    assert body["accessible"]["risk"] is None
    assert "The weather forecast is unavailable." in body["warnings"]
    assert len(calls) == 2


@pytest.mark.parametrize("patch", [
    {"from": [181, 43]}, {"to": [-79, 91]}, {"from": ["nan", 43]},
    {"from": [-79]}, {"profile": "skateboard"}, {"to": TRIP["from"]}, {"demo_barrier_ids": []},
])
def test_plan_rejects_unusable_inputs(patch):
    assert client.post("/plan", json={**TRIP, **patch}).status_code == 422


def test_barriers_filter_by_bbox_and_kind():
    body = client.get("/barriers", params={"bbox": "-79.39,43.65,-79.37,43.67", "kind": "sidewalk"}).json()
    assert body["data_source"] == "fixtures"
    assert [feature["properties"]["id"] for feature in body["features"]] == [1]
    assert client.get("/barriers", params={"bbox": "0,0,1,1"}).json()["features"] == []


@pytest.mark.parametrize("bbox", ["x,y,z,w", "-79,43,-80,44", "0,0,1", "nan,0,1,1", "-200,0,1,1"])
def test_barriers_reject_malformed_bbox(bbox):
    assert client.get("/barriers", params={"bbox": bbox}).status_code == 422


def test_missing_key_is_reported(monkeypatch):
    monkeypatch.setattr(settings, "ors_api_key", "")
    response = client.post("/plan", json=TRIP)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "routing_not_configured"


@pytest.mark.parametrize("status,data,expected", [
    (429, {"error": {"message": "rate limited"}}, 503),
    (403, {"error": "Quota exceeded"}, 503),
    (200, {"features": []}, 502),
    (200, {"features": [{"geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}}]}, 502),
])
def test_provider_failures_are_errors(monkeypatch, status, data, expected):
    provider(monkeypatch, lambda profile, body: (status, data))
    assert client.post("/plan", json=TRIP).status_code == expected


def test_route_crossing_verified_closure_is_rejected(monkeypatch, tmp_path):
    use_polygon(monkeypatch, tmp_path)
    provider(monkeypatch, ok)
    assert client.post("/plan", json=TRIP).status_code == 409


def test_reported_polygon_does_not_become_a_routing_constraint(monkeypatch, tmp_path):
    use_polygon(monkeypatch, tmp_path, verification="reported")
    calls = provider(monkeypatch, ok)
    response = client.post("/plan", json={**TRIP, "avoid_risk": False})
    assert response.status_code == 200
    assert response.json()["accessible"]["avoided_barrier_ids"] == []
    assert "avoid_polygons" not in calls[1]["json"]["options"]


def test_detour_outside_original_area_is_checked(monkeypatch, tmp_path):
    use_polygon(monkeypatch, tmp_path, coordinates=[[-79.4405, 43.6585], [-79.4395, 43.6585], [-79.4395, 43.6595], [-79.4405, 43.6595], [-79.4405, 43.6585]])
    provider(monkeypatch, lambda profile, body: (200, ors_route([TRIP["from"], [-79.44, 43.659], TRIP["to"]], distance=12000)))
    assert client.post("/plan", json=TRIP).status_code == 409


def test_provider_timeout_is_reported(monkeypatch):
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("provider timed out")
    monkeypatch.setattr(httpx, "post", timeout)
    assert client.post("/plan", json=TRIP).status_code == 504


def test_database_failure_never_falls_back_to_fixtures(monkeypatch):
    monkeypatch.setattr(settings, "barrier_source", "postgres")
    def unavailable():
        raise psycopg.OperationalError("database unavailable")
    monkeypatch.setattr(barriers, "get_pool", unavailable)
    assert client.get("/barriers").status_code == 503
    assert client.post("/plan", json=TRIP).status_code == 503


def test_risk_endpoint_filters_cells_by_bbox():
    body = client.get("/risk", params={"bbox": "-79.3825,43.654,-79.381,43.6555"}).json()
    assert body["date"] == "2026-10-17"
    assert [feature["properties"]["cell"] for feature in body["features"]] == ["middle"]
    assert client.get("/risk", params={"bbox": "x,y,z,w"}).status_code == 422


def test_geocode_returns_toronto_suggestions(monkeypatch):
    calls = []
    def get(url, **kwargs):
        calls.append(kwargs)
        return httpx.Response(200, json={"features": [{
            "geometry": {"type": "Point", "coordinates": [-79.3806, 43.6453]},
            "properties": {"label": "Union Station, Toronto, ON, Canada"},
        }]}, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", get)
    body = client.get("/geocode", params={"text": "union"}).json()
    assert body == {"results": [{"label": "Union Station, Toronto, ON, Canada", "coordinates": [-79.3806, 43.6453]}]}
    assert calls[0]["params"]["boundary.rect.min_lon"] == barriers.TORONTO_BBOX[0]
    assert client.get("/geocode", params={"text": "u"}).status_code == 422


def test_geocode_failure_is_reported(monkeypatch):
    def get(url, **kwargs):
        return httpx.Response(500, json={}, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", get)
    assert client.get("/geocode", params={"text": "union"}).status_code == 502


def test_routing_cache_keeps_only_the_most_recent_answers(monkeypatch):
    monkeypatch.setattr(routing, "CACHE_SIZE", 3)
    calls = provider(monkeypatch, ok)
    for offset in range(5):
        routing.ors("foot-walking", [TRIP["from"], [TRIP["to"][0] + offset * 1e-4, TRIP["to"][1]]])
    assert len(routing._cache) == 3 and len(calls) == 5
    routing.ors("foot-walking", [TRIP["from"], [TRIP["to"][0] + 4e-4, TRIP["to"][1]]])
    assert len(calls) == 5  # the newest answer is still cached
