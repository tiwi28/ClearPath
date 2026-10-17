from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
TRIP = {"from": [-79.3832, 43.6534], "to": [-79.3802, 43.6561], "include_transit": False}


def test_only_navigation_endpoints_are_exposed():
    assert set(client.get("/openapi.json").json()["paths"]) == {
        "/health", "/barriers", "/geocode", "/plan", "/risk", "/stations",
        "/wards", "/wards/locate", "/wards/{ward_id}", "/trip/hazards", "/reports",
    }


def test_ward_reporting_api_is_removed():
    assert client.get("/wards/13/report").status_code == 404


def test_station_api_is_removed():
    assert client.post("/stations/test/elevator", json={"status": "out_of_service"}).status_code == 404


def test_plan_needs_only_endpoints():
    response = client.post("/plan", json=TRIP)
    assert response.status_code == 200
    assert response.json()["accessible"]["distance_m"] == 920


def test_old_demo_scaffolding_is_rejected():
    assert client.post("/plan", json={**TRIP, "demo_barrier_ids": []}).status_code == 422


def test_barrier_data_contains_no_hidden_demo_features():
    assert all(feature["properties"]["source"] != "demo" for feature in client.get("/barriers").json()["features"])
