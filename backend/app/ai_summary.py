"""The "In plain words" paragraph on a ward report card.

Gemini writes it from the ward's numbers only. If there is no key, the call fails, or the
text mentions a number that is not in the input, a template sentence built from the same
numbers is used instead, so the card never shows an invented figure.
"""

import json
import re
from datetime import date

import httpx

from .config import settings

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
INSTRUCTIONS = (
    "You write the 'In plain words' summary on a nonpartisan City of Toronto ward report card about "
    "sidewalk accessibility. Use only the facts in the JSON you are given. Write 2 or 3 short, plain "
    "sentences for residents. Do not mention candidates, parties, councillors, elections, or other "
    "wards, and do not rank or judge the ward. Do not use any number that is not in the JSON. "
    "Say 'reports' or 'people reported', never 'problems', because 311 counts reflect what people "
    "reported. Skip any fact whose value is null."
)
_cache: dict[tuple[int, date], tuple[str, str]] = {}


def facts(card: dict) -> dict:
    live = card["live"]
    top = card["top_places"][0]["place"] if card["top_places"] else None
    return {
        "ward": card["name"],
        "snow_or_ice_reports_last_winter": card["snow_last_winter"],
        "damaged_sidewalk_or_curb_reports_past_12_months": card["damage_12m"],
        "ramp_or_tactile_paver_reports_past_12_months": card["ramps_12m"],
        "place_with_most_reports_past_12_months": top,
        "share_of_past_12_month_reports_still_open_percent": round(card["open_share_12m"] * 100),
        "ttc_subway_stations_in_ward": live["elevators"].get("stations"),
        "ttc_elevators_out_now": live["elevators"]["out"] if live["elevators"]["available"] else None,
        "active_road_or_sidewalk_closures_now": live["closures"]["count"] if live["closures"]["available"] else None,
    }


def template(card: dict) -> str:
    f = facts(card)
    sentences = [f"Last winter, people in this ward filed {f['snow_or_ice_reports_last_winter']} reports about "
                 "sidewalks not cleared of snow or ice."]
    damage = (f"In the past 12 months there were {f['damaged_sidewalk_or_curb_reports_past_12_months']} reports "
              "of damaged sidewalks or curbs")
    sentences.append(damage + (f", most often near {f['place_with_most_reports_past_12_months']}."
                               if f["place_with_most_reports_past_12_months"] else "."))
    if f["ttc_subway_stations_in_ward"] == 0:
        sentences.append("There are no TTC subway or LRT stations in this ward.")
    elif f["ttc_elevators_out_now"] is not None:
        out = f["ttc_elevators_out_now"]
        sentences.append("Right now no TTC elevators in the ward are reported out of service." if out == 0 else
                         f"Right now {out} TTC elevator{'s are' if out != 1 else ' is'} out of service in the ward.")
    return " ".join(sentences)


def _numbers_ok(text: str, values: dict) -> bool:
    allowed = {str(v) for v in values.values() if isinstance(v, (int, float))} | {"311", "12"}
    return all(number.replace(",", "") in allowed for number in re.findall(r"\d[\d,]*", text))


def _gemini(values: dict) -> str | None:
    try:
        response = httpx.post(
            GEMINI_URL.format(model=settings.gemini_model),
            headers={"x-goog-api-key": settings.gemini_api_key},
            json={"systemInstruction": {"parts": [{"text": INSTRUCTIONS}]},
                  "contents": [{"role": "user", "parts": [{"text": json.dumps(values)}]}],
                  "generationConfig": {"temperature": 0.2, "maxOutputTokens": 600,
                                       "thinkingConfig": {"thinkingBudget": 0}}},
            timeout=20,
        )
        response.raise_for_status()
        candidate = response.json()["candidates"][0]
        text = "".join(part.get("text", "") for part in candidate["content"]["parts"]).strip()
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return None
    # A cut-off answer (token limit, safety stop) must never reach the card.
    finished = candidate.get("finishReason") == "STOP" and text.endswith((".", "!", "?"))
    return text if finished and _numbers_ok(text, values) else None


def summarize(card: dict) -> tuple[str, str]:
    """(text, source) where source is 'gemini' or 'template'. Cached per ward per day."""
    key = (card["id"], date.today())
    if key not in _cache:
        text = _gemini(facts(card)) if settings.gemini_api_key.strip() else None
        _cache[key] = (text, "gemini") if text else (template(card), "template")
    return _cache[key]
