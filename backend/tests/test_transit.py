import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import transit, ttc
from app.main import app
from app.profiles import PROFILES

client = TestClient(app)
FIXTURES = Path(__file__).parent / "fixtures"
PLAN = json.loads((FIXTURES / "transitous_plan.json").read_text())  # Union -> Museum via King, wheelchair profile
ALERTS = json.loads((FIXTURES / "ttc_alerts.json").read_text())
NOW = datetime(2026, 10, 17, 9, tzinfo=timezone.utc)
BUS_ONLY = {"itineraries": [{
    "startTime": "2026-10-17T14:00:00Z", "endTime": "2026-10-17T14:30:00Z", "duration": 1800, "transfers": 0,
    "legs": [{"mode": "BUS", "routeShortName": "320", "routeColor": "da251d", "headsign": "320 Yonge",
              "from": {"name": "Yonge St at Front St E"}, "to": {"name": "Yonge St at Bloor St E"},
              "startTime": "2026-10-17T14:00:00Z", "endTime": "2026-10-17T14:30:00Z", "duration": 1800,
              "distance": 3000, "legGeometry": {"points": "_p~iF~ps|U_ulLnnqC", "precision": 5}}],
}]}


def transitous(monkeypatch, surface=BUS_ONLY):
    calls = []
    def get(url, **kwargs):
        calls.append(kwargs.get("params", {}))
        if "alerts.ttc.ca" in url:
            return httpx.Response(200, json=ALERTS, request=httpx.Request("GET", url))
        body = surface if kwargs["params"].get("transitModes") else PLAN
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", get)
    return calls


def test_decode_polyline():
    assert transit.decode("_p~iF~ps|U_ulLnnqC_mqNvxq`@", 5) == [[-120.2, 38.5], [-120.95, 40.7], [-126.453, 43.252]]


@pytest.mark.parametrize("name,key", [
    ("Union Station - Northbound Platform Towards Finch", "union"), ("St. George", "st george"),
    ("Bloor Station - Southbound Platform", "bloor-yonge"), ("Yonge Station", "bloor-yonge"),
    ("Queen's Park Station - Northbound Platform", "queen's park"),
])
def test_station_names_normalize(name, key):
    assert ttc.station_key(name) == key


def test_station_list_marks_stations_without_elevators():
    stations = ttc.stations()
    assert stations["union"]["has_elevator"] is True
    assert {key for key, station in stations.items() if not station["has_elevator"]} == {
        "college", "islington", "king", "museum", "old mill"}


def test_alerts_parse_outages_and_closures():
    alerts = ttc.parse_alerts(ALERTS, NOW)
    eglinton = [outage for outage in alerts["outages"] if outage["station_key"] == "eglinton"]
    assert {outage["kind"] for outage in eglinton} == {"elevator", "escalator"}
    assert any(closure["line"] == "1" and "eglinton" in closure["stations"] for closure in alerts["closures"])


def test_wheelchair_trips_through_stations_without_elevators_are_replaced(monkeypatch):
    calls = transitous(monkeypatch)
    options, notes = transit.plan(PROFILES["manual_wheelchair"], (-79.3806, 43.6453), (-79.394, 43.667), [])
    assert notes == ["Hid 3 trips through stations without a working elevator (King, Museum)."]
    assert [leg["line"] for option in options for leg in option["legs"]] == ["320"]
    assert calls[-1]["transitModes"] == transit.SURFACE_MODES
    assert calls[-1]["pedestrianProfile"] == "WHEELCHAIR"


def test_walker_keeps_trips_and_sees_station_warnings(monkeypatch):
    calls = transitous(monkeypatch)
    options, notes = transit.plan(PROFILES["walker"], (-79.3806, 43.6453), (-79.394, 43.667), [])
    assert notes == []
    assert len(options) == 1  # three identical itineraries collapse into one
    texts = [issue["text"] for issue in options[0]["issues"]]
    assert "King has no elevator" in texts and "Museum has no elevator" in texts
    assert all(issue["severity"] == "warning" for issue in options[0]["issues"])
    assert options[0]["legs"][1]["color"] == "#d5c82b"
    assert options[0]["legs"][1]["geometry"]["coordinates"][0] == pytest.approx([-79.379684, 43.645847], abs=1e-5)
    assert calls[-1]["pedestrianSpeed"] == 0.9


def test_plan_includes_transit_and_survives_transitous_failure(monkeypatch):
    transitous(monkeypatch)
    trip = {"from": [-79.41, 43.66], "to": [-79.42, 43.665], "profile": "walker"}  # clear of the fixture barriers
    body = client.post("/plan", json=trip).json()
    assert body["transit"][0]["legs"][1]["line"] == "1"

    def down(url, **kwargs):
        if "transitous" in url:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json=ALERTS, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", down)
    response = client.post("/plan", json=trip)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transit"] == []
    assert any("TTC trip planning is unavailable" in warning for warning in body["warnings"])


def test_stations_endpoint_reports_live_outages(monkeypatch):
    transitous(monkeypatch)
    body = client.get("/stations").json()
    eglinton = next(station for station in body["stations"] if station["name"] == "Eglinton")
    assert any(outage["kind"] == "elevator" for outage in eglinton["outages"])
    assert body["alerts_available"] is True
