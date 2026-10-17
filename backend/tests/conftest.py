import json
from pathlib import Path

import httpx
import pytest

from app import forecast, reports, restrictions, routing, ttc
from app.config import settings

FIXTURES = Path(__file__).parent / "fixtures"


def cell(west, south, east, north, value, name):
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"cell": name, "risk": value, "reports_last_year": 3}}


# Small risk grid around the test trip: a high-risk cell mid-route, a high-risk cell
# holding the start point, and a low-risk cell holding the destination.
RISK_CELLS = [
    cell(-79.3822, 43.6544, -79.3812, 43.6551, 0.5, "middle"),
    cell(-79.3836, 43.6530, -79.3828, 43.6538, 0.4, "start"),
    cell(-79.3806, 43.6557, -79.3798, 43.6565, 0.02, "destination"),
]


def risk_map(day=None):
    return {"date": "2026-10-17", "generated_at": "2026-10-17T09:00", "reports_through": "2026-09-30",
            "weather": {}, "weather_source": "test", "model": {}, "warnings": [], "features": RISK_CELLS}


def ors_route(coordinates, distance=920, waytypes=None):
    return {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "properties": {"summary": {"distance": distance, "duration": 810},
                       "segments": [{"steps": [{"instruction": "Continue north.", "distance": distance}]}],
                       "extras": {"waytype": {"values": waytypes or []}}},
    }]}


@pytest.fixture(autouse=True)
def controlled_dependencies(monkeypatch):
    """API tests never need real credentials, network calls, or a database."""
    monkeypatch.setattr(settings, "ors_api_key", "test-key")
    monkeypatch.setattr(settings, "barrier_source", "fixtures")
    monkeypatch.setattr(forecast, "predict", risk_map)
    monkeypatch.setattr(reports, "recent", lambda bounds: [])
    monkeypatch.setattr(restrictions, "active", lambda: {"available": True, "items": []})
    routing._cache.clear()
    ttc._alerts_cache.update(fetched=0.0, value=None)

    def post(url, **kwargs):
        return httpx.Response(200, json=ors_route(kwargs["json"]["coordinates"]), request=httpx.Request("POST", url))

    def get(url, **kwargs):
        if "transitous" in url:
            body = {"itineraries": []}
        elif "alerts.ttc.ca" in url:
            body = json.loads((FIXTURES / "ttc_alerts.json").read_text())
        else:
            raise AssertionError(f"unexpected GET {url}")
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(httpx, "get", get)
