import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import ai_summary, restrictions, wards, write_summaries
from app.config import settings
from app.main import app

client = TestClient(app)
CN_TOWER = (-79.3871, 43.6426)  # Spadina-Fort York, ward 10


@pytest.fixture(autouse=True)
def stored_summaries(monkeypatch, tmp_path):
    """Each test starts with no stored summaries and must never call Gemini while a card loads."""
    monkeypatch.setattr(ai_summary, "SUMMARIES_PATH", tmp_path / "ward_summaries.json")
    monkeypatch.setattr(restrictions, "active", lambda: {"available": True, "items": []})

    def no_gemini(url, **kwargs):
        raise AssertionError(f"unexpected POST {url}")
    monkeypatch.setattr(httpx, "post", no_gemini)
    return tmp_path / "ward_summaries.json"


def store(path, ward_id, **entry):
    path.write_text(json.dumps({"wards": {str(ward_id): entry}}))


def test_lists_all_25_wards():
    wards_list = client.get("/wards").json()["wards"]
    assert [ward["id"] for ward in wards_list] == list(range(1, 26))


def test_locates_a_point_in_its_ward_and_rejects_points_outside_toronto():
    assert client.get("/wards/locate", params={"lng": CN_TOWER[0], "lat": CN_TOWER[1]}).json()["id"] == 10
    assert client.get("/wards/locate", params={"lng": -80.5, "lat": 43.4}).status_code == 404


def test_card_has_city_numbers_live_numbers_and_a_template_summary_when_none_is_stored():
    card = client.get("/wards/10").json()
    assert card["name"] == "Spadina-Fort York"
    assert card["snow_last_winter"] >= 0 and len(card["monthly"]) == 24
    assert card["live"]["closures"] == {"available": True, "count": 0, "sidewalk": 0, "road_closed": 0}
    assert card["live"]["elevators"]["available"] is True and card["live"]["elevators"]["stations"] > 0
    assert card["live"]["forecast"]["available"] is True
    assert card["summary_source"] == "template"
    assert str(card["snow_last_winter"]) in card["summary"]
    assert "No road or sidewalk closures are active" in card["summary_live"]
    assert len(card["data_version"]) == 12


def test_unavailable_feeds_are_reported_as_unavailable_not_zero(monkeypatch):
    monkeypatch.setattr(restrictions, "active", lambda: {"available": False, "items": []})
    card = client.get("/wards/10").json()
    assert card["live"]["closures"] == {"available": False}
    assert "closure" not in (card["summary_live"] or "")


def test_unknown_ward_is_a_404():
    assert client.get("/wards/26").status_code == 404


def test_stored_summary_is_used_while_its_numbers_still_match(stored_summaries):
    values = wards.static_facts(wards.load(), 10)
    store(stored_summaries, 10, facts_hash=ai_summary.fingerprint(values), source="gemini", text="Stored words.")
    card = client.get("/wards/10").json()
    assert (card["summary"], card["summary_source"]) == ("Stored words.", "gemini")


def test_stored_summary_for_older_numbers_falls_back_to_the_template(stored_summaries):
    store(stored_summaries, 10, facts_hash="0000000000000000", source="gemini", text="Old words.")
    assert client.get("/wards/10").json()["summary_source"] == "template"


def test_card_is_cacheable_and_revalidates_with_an_etag():
    first = client.get("/wards/10")
    assert "max-age=60" in first.headers["cache-control"]
    again = client.get("/wards/10", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and again.content == b""
    assert "max-age=86400" in client.get("/wards").headers["cache-control"]


def test_writer_only_sends_changed_wards_to_gemini(stored_summaries):
    calls = []

    def generate(values):
        calls.append(values["ward"])
        return f"{values['ward']} summary."

    first = write_summaries.run(generate=generate)
    assert len(first["written"]) == 25 and len(calls) == 25
    calls.clear()
    assert write_summaries.run(generate=generate)["kept"] == list(range(1, 26)) and calls == []

    saved = json.loads(stored_summaries.read_text())
    saved["wards"]["7"]["facts_hash"] = "changed"
    stored_summaries.write_text(json.dumps(saved))
    assert write_summaries.run(generate=generate)["written"] == [7] and len(calls) == 1


def test_writer_stores_failures_as_templates_and_retries_them_next_run(stored_summaries):
    result = write_summaries.run(generate=lambda values: None, attempts=1)
    assert len(result["failed"]) == 25
    assert client.get("/wards/10").json()["summary_source"] == "template"
    assert len(write_summaries.run(generate=lambda values: "Fine.", attempts=1)["written"]) == 25


def test_writer_stops_at_a_daily_quota_and_keeps_its_progress(stored_summaries):
    calls = []

    def generate(values):
        calls.append(1)
        if len(calls) > 3:
            raise ai_summary.QuotaExceeded(14000)
        return "Fine."

    first = write_summaries.run(generate=generate)
    assert first["written"] == [1, 2, 3] and first["pending"] == list(range(4, 26)) and len(calls) == 4
    second = write_summaries.run(generate=lambda values: "Fine.")
    assert second["kept"] == [1, 2, 3] and second["written"] == list(range(4, 26))


def test_writer_waits_out_a_short_rate_limit_without_losing_an_attempt(stored_summaries):
    replies, waits = iter([ai_summary.QuotaExceeded(5), "Fine."] + ["Fine."] * 24), []

    def generate(values):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    result = write_summaries.run(generate=generate, attempts=1, sleep=waits.append)
    assert waits == [5] and len(result["written"]) == 25


def test_gemini_quota_is_raised_with_its_retry_delay(monkeypatch):
    def post(url, **kwargs):
        body = {"error": {"details": [{"@type": "RetryInfo", "retryDelay": "14158s"}]}}
        return httpx.Response(429, json=body, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    with pytest.raises(ai_summary.QuotaExceeded) as error:
        ai_summary.generate(wards.static_facts(wards.load(), 10))
    assert error.value.retry_after == 14158


def gemini_reply(monkeypatch, text, finish="STOP"):
    def post(url, **kwargs):
        assert "generativelanguage" in url
        body = {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}]}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)


def test_gemini_text_is_kept_when_it_only_uses_given_numbers(monkeypatch):
    values = wards.static_facts(wards.load(), 10)
    gemini_reply(monkeypatch, f"People filed {values['snow_or_ice_reports_last_winter']} snow reports last winter.")
    assert ai_summary.generate(values) is not None


@pytest.mark.parametrize("text,finish", [("People filed 99999 reports.", "STOP"), ("People filed", "MAX_TOKENS")])
def test_gemini_text_is_rejected_when_it_invents_a_number_or_is_cut_off(monkeypatch, text, finish):
    gemini_reply(monkeypatch, text, finish)
    assert ai_summary.generate(wards.static_facts(wards.load(), 10)) is None


def test_ward_data_is_reloaded_when_a_file_changes(stored_summaries):
    before = wards.load()
    store(stored_summaries, 1, facts_hash="x", source="template", text=None)
    assert wards.load() is not before and wards.load().summaries == {"1": {"facts_hash": "x", "source": "template", "text": None}}


def test_restriction_feed_parses_bad_escapes_and_keeps_only_active_items():
    feed = ('{"Closure":[{"id":"a","type":"ROAD_CLOSED","name":"Sidewalk closed \\ at King","expired":0,'
            '"startTime":"0","endTime":"9999999999999","geoPolyline":"[-79.38,43.64],[-79.37,43.64]"},'
            '{"id":"b","type":"CONSTRUCTION","expired":1,"startTime":"0","endTime":"1","latitude":"43.6","longitude":"-79.4"}]}')
    items = restrictions.parse(feed, now_ms=1000)
    assert [item["id"] for item in items] == ["a"]
    assert items[0]["sidewalk"] is True and items[0]["geometry"].geom_type == "LineString"


def test_no_key_means_the_writer_does_nothing(monkeypatch, capsys):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr("sys.argv", ["write_summaries"])
    assert write_summaries.main() == 1
    assert "GEMINI_API_KEY is not set" in capsys.readouterr().err
