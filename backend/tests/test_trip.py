import time
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from psycopg_pool import PoolTimeout
from shapely.geometry import LineString

from app import barriers, reports, restrictions
from app.main import app
from conftest import ors_route

client = TestClient(app)
REAL_RECENT = reports.recent  # conftest replaces reports.recent; these tests need the real one
NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
SPOT = (-79.3820, 43.6547)
# A straight trip through the conftest "middle" risk cell (risk 0.5), passing SPOT.
ROUTE = [[-79.3832, 43.6540], [-79.3802, 43.6554]]


def report(report_id, device, state="blocked", hours_ago=1, at=SPOT, kind="blocked_sidewalk"):
    return {"id": report_id, "created_at": NOW - timedelta(hours=hours_ago), "device_id": device,
            "kind": kind, "state": state, "lng": at[0], "lat": at[1]}


def test_one_blocked_report_shows_the_spot_without_blocking_routes():
    [spot] = reports.spots([report(1, "device-a")], NOW)
    assert spot["properties"]["verification"] == "reported" and spot["properties"]["blocks_route"] is False
    assert spot["geometry"]["type"] == "Point"


def test_two_devices_confirm_a_spot_and_routing_treats_it_as_a_barrier():
    nearby = (SPOT[0] + 0.0001, SPOT[1])  # about 8 m away: the same spot
    [spot] = reports.spots([report(1, "device-a"), report(2, "device-b", at=nearby)], NOW)
    assert spot["properties"]["verification"] == "rider_confirmed" and spot["properties"]["id"] == -1
    assert spot["geometry"]["type"] == "Polygon"
    assert barriers.blockers([spot]) == [spot]


def test_the_same_device_twice_does_not_confirm():
    [spot] = reports.spots([report(1, "device-a"), report(2, "device-a")], NOW)
    assert spot["properties"]["blocks_route"] is False


def test_a_newer_clear_report_closes_the_spot_and_old_reports_expire():
    assert reports.spots([report(1, "device-a", hours_ago=3), report(2, "device-b", state="clear", hours_ago=1)], NOW) == []
    assert reports.spots([report(1, "device-a", hours_ago=60)], NOW) == []


def test_far_apart_reports_are_separate_spots():
    far = (SPOT[0] + 0.002, SPOT[1])  # about 160 m away
    assert len(reports.spots([report(1, "device-a"), report(2, "device-b", at=far)], NOW)) == 2


def test_confirmed_rider_spots_reach_the_router(monkeypatch):
    monkeypatch.setattr(reports, "recent", lambda bounds: [report(1, "device-a"), report(2, "device-b")])
    calls = []

    def post(url, **kwargs):
        import httpx
        calls.append(kwargs["json"])
        return httpx.Response(200, json=ors_route(kwargs["json"]["coordinates"]), request=httpx.Request("POST", url))

    import httpx
    monkeypatch.setattr(httpx, "post", post)
    body = client.post("/plan", json={"from": ROUTE[0], "to": ROUTE[1], "include_transit": False, "avoid_risk": False}).json()
    assert -1 in body["accessible"]["avoided_barrier_ids"]
    assert any("avoid_polygons" in call.get("options", {}) for call in calls)


def test_hazards_are_ordered_along_the_route(monkeypatch):
    monkeypatch.setattr(reports, "recent", lambda bounds: [report(1, "device-a")])
    closure = {"id": "c1", "type": "ROAD_CLOSED", "road": "Test St", "label": "Test St closed", "impact": "High",
               "sidewalk": True, "geometry": LineString([(-79.3805, 43.6550), (-79.3805, 43.6556)])}
    monkeypatch.setattr(restrictions, "active", lambda: {"available": True, "items": [closure]})
    hazards = client.post("/trip/hazards", json={"route": {"type": "LineString", "coordinates": ROUTE}}).json()["hazards"]
    kinds = [h["kind"] for h in hazards]
    assert kinds == ["forecast", "rider_report", "closure"]
    assert hazards == sorted(hazards, key=lambda h: h["at_m"])
    assert hazards[1]["label"].endswith("reported by 1 rider")


def test_report_validation_rejects_unknown_kinds():
    response = client.post("/reports", json={"device_id": "device-abc", "kind": "pothole", "state": "blocked", "location": SPOT})
    assert response.status_code == 422


def test_steps_carry_turn_types_and_route_indices(monkeypatch):
    import httpx

    def post(url, **kwargs):
        body = ors_route(kwargs["json"]["coordinates"])
        body["features"][0]["properties"]["segments"][0]["steps"] = [
            {"instruction": "Head east", "distance": 900, "type": 11, "way_points": [0, 1]},
            {"instruction": "Arrive", "distance": 0, "type": 10, "way_points": [1, 1]}]
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    steps = client.post("/plan", json={"from": ROUTE[0], "to": ROUTE[1], "include_transit": False}).json()["accessible"]["steps"]
    assert steps[0] == {"instruction": "Head east", "distance_m": 900, "way_points": [0, 1], "type": 11}


def test_reports_outside_toronto_are_rejected():
    body = {"device_id": "device-abc123", "kind": "other", "state": "blocked", "location": [-73.57, 45.50]}
    assert client.post("/reports", json=body).status_code == 422


def test_one_address_can_only_send_so_many_reports(monkeypatch):
    monkeypatch.setattr(reports, "_by_address", reports.defaultdict(reports.deque))
    assert all(reports._allow_address("203.0.113.9") for _ in range(reports.IP_RATE_LIMIT))
    assert reports._allow_address("203.0.113.9") is False
    assert reports._allow_address("198.51.100.4") is True


def test_an_unreachable_database_never_slows_barrier_queries(monkeypatch):
    calls = []

    def down():
        calls.append(1)
        raise PoolTimeout("database unavailable")
    monkeypatch.setattr(reports, "recent", REAL_RECENT)
    monkeypatch.setattr(reports, "_pool", down)
    started = time.time()
    for _ in range(5):
        assert barriers.query_features(barriers.route_bounds(ROUTE)) != []  # fixture barriers still come back
    assert len(calls) == 1 and time.time() - started < 1


def test_recent_reports_are_filtered_to_the_requested_area(monkeypatch):
    monkeypatch.setattr(reports, "recent", REAL_RECENT)
    monkeypatch.setattr(reports.REPORTS, "get", lambda: [report(1, "device-a"), report(2, "device-b", at=(-79.5, 43.7))])
    assert [r["id"] for r in reports.recent(barriers.route_bounds(ROUTE))] == [1]
