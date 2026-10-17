import httpx
import pytest
from fastapi.testclient import TestClient

from app import ai_summary, restrictions
from app.config import settings
from app.main import app

client = TestClient(app)
CN_TOWER = (-79.3871, 43.6426)  # Spadina-Fort York, ward 10


@pytest.fixture(autouse=True)
def no_live_feeds(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(restrictions, "active", lambda: {"available": True, "items": []})
    ai_summary._cache.clear()


def test_lists_all_25_wards():
    wards = client.get("/wards").json()["wards"]
    assert [ward["id"] for ward in wards] == list(range(1, 26))


def test_locates_a_point_in_its_ward_and_rejects_points_outside_toronto():
    assert client.get("/wards/locate", params={"lng": CN_TOWER[0], "lat": CN_TOWER[1]}).json()["id"] == 10
    assert client.get("/wards/locate", params={"lng": -80.5, "lat": 43.4}).status_code == 404


def test_card_has_city_numbers_live_numbers_and_a_template_summary_without_a_key():
    card = client.get("/wards/10").json()
    assert card["name"] == "Spadina-Fort York"
    assert card["snow_last_winter"] >= 0 and len(card["monthly"]) == 24
    assert card["live"]["closures"] == {"available": True, "count": 0, "sidewalk": 0, "road_closed": 0}
    assert card["live"]["forecast"]["available"] is True
    assert card["summary_source"] == "template"
    assert str(card["snow_last_winter"]) in card["summary"]


def test_unavailable_feeds_are_reported_as_unavailable_not_zero(monkeypatch):
    monkeypatch.setattr(restrictions, "active", lambda: {"available": False, "items": []})
    assert client.get("/wards/10").json()["live"]["closures"] == {"available": False}


def test_unknown_ward_is_a_404():
    assert client.get("/wards/26").status_code == 404


def gemini_reply(monkeypatch, text, finish="STOP"):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    def post(url, **kwargs):
        assert "generativelanguage" in url
        body = {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}]}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)


def test_uses_gemini_text_when_it_only_uses_given_numbers(monkeypatch):
    card = client.get("/wards/10").json()
    ai_summary._cache.clear()
    gemini_reply(monkeypatch, f"People filed {card['snow_last_winter']} snow reports last winter.")
    card = client.get("/wards/10").json()
    assert card["summary_source"] == "gemini"


@pytest.mark.parametrize("text,finish", [("People filed 99999 reports.", "STOP"), ("People filed", "MAX_TOKENS")])
def test_falls_back_when_gemini_invents_a_number_or_is_cut_off(monkeypatch, text, finish):
    gemini_reply(monkeypatch, text, finish)
    assert client.get("/wards/10").json()["summary_source"] == "template"


def test_restriction_feed_parses_bad_escapes_and_keeps_only_active_items():
    feed = ('{"Closure":[{"id":"a","type":"ROAD_CLOSED","name":"Sidewalk closed \\ at King","expired":0,'
            '"startTime":"0","endTime":"9999999999999","geoPolyline":"[-79.38,43.64],[-79.37,43.64]"},'
            '{"id":"b","type":"CONSTRUCTION","expired":1,"startTime":"0","endTime":"1","latitude":"43.6","longitude":"-79.4"}]}')
    items = restrictions.parse(feed, now_ms=1000)
    assert [item["id"] for item in items] == ["a"]
    assert items[0]["sidewalk"] is True and items[0]["geometry"].geom_type == "LineString"
