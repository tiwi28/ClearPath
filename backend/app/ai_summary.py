"""The "In plain words" paragraph on a ward report card.

Written ahead of time, never while a card loads: `python -m app.write_summaries` asks Gemini
for one paragraph per ward from the ward's City 311 numbers and stores it in
ward_summaries.json with a fingerprint of those numbers. A card uses the stored text only
while the fingerprint still matches. Otherwise (new data, no key, a failed or unsafe answer)
it uses a template built from the same numbers, so it never shows an invented figure.

Live numbers (elevators out, closures) change by the minute, so they get their own template
sentence on every request instead of going through Gemini.
"""

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

import httpx

from .config import settings

SUMMARIES_PATH = Path(__file__).parent / "data" / "ward_summaries.json"
PROMPT_VERSION = 2  # bump when INSTRUCTIONS or facts() change, so every summary is rewritten
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
INSTRUCTIONS = (
    "You write the 'In plain words' summary on a nonpartisan City of Toronto ward report card about "
    "sidewalk accessibility. Use only the facts in the JSON you are given. Write 2 or 3 short, plain "
    "sentences for residents. Do not mention candidates, parties, councillors, elections, or other "
    "wards, and do not rank or judge the ward. Do not use any number that is not in the JSON. "
    "Say 'reports' or 'people reported', never 'problems', because 311 counts reflect what people "
    "reported. Skip any fact whose value is null."
)


def facts(ward: dict) -> dict:
    """The static numbers a summary may use: City 311 counts and the ward's station count."""
    top = ward["top_places"][0]["place"] if ward["top_places"] else None
    return {
        "ward": ward["name"],
        "snow_or_ice_reports_last_winter": ward["snow_last_winter"],
        "damaged_sidewalk_or_curb_reports_past_12_months": ward["damage_12m"],
        "ramp_or_tactile_paver_reports_past_12_months": ward["ramps_12m"],
        "place_with_most_reports_past_12_months": top,
        "share_of_past_12_month_reports_still_open_percent": round(ward["open_share_12m"] * 100),
        "ttc_subway_stations_in_ward": ward["station_count"],
    }


def fingerprint(values: dict) -> str:
    """Changes whenever the numbers or the prompt change, which is when a summary must be rewritten."""
    payload = json.dumps({"prompt": PROMPT_VERSION, "facts": values}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def template(values: dict) -> str:
    sentences = [f"Last winter, people in this ward filed {values['snow_or_ice_reports_last_winter']} reports about "
                 "sidewalks not cleared of snow or ice."]
    damage = (f"In the past 12 months there were {values['damaged_sidewalk_or_curb_reports_past_12_months']} reports "
              "of damaged sidewalks or curbs")
    place = values["place_with_most_reports_past_12_months"]
    sentences.append(damage + (f", most often near {place}." if place else "."))
    if values["ttc_subway_stations_in_ward"] == 0:
        sentences.append("There are no TTC subway or LRT stations in this ward.")
    return " ".join(sentences)


def live_sentence(live: dict, station_count: int) -> str | None:
    """Right-now elevators and closures, from the card's live numbers. None if no feed is available."""
    sentences = []
    elevators, closures = live["elevators"], live["closures"]
    if station_count and elevators["available"]:
        out = elevators["out"]
        sentences.append("Right now no TTC elevators in the ward are reported out of service." if out == 0 else
                         f"Right now {out} TTC elevator{'s are' if out != 1 else ' is'} out of service in the ward.")
    if closures["available"]:
        count = closures["count"]
        sentences.append("No road or sidewalk closures are active in the ward." if count == 0 else
                         f"{count} road or sidewalk closure{'s are' if count != 1 else ' is'} active in the ward.")
    return " ".join(sentences) or None


def summarize(values: dict, stored: dict | None) -> tuple[str, str]:
    """(text, source): the stored Gemini text if it was written from these exact numbers, else the template."""
    if stored and stored.get("source") == "gemini" and stored.get("facts_hash") == fingerprint(values):
        return stored["text"], "gemini"
    return template(values), "template"


def _numbers_ok(text: str, values: dict) -> bool:
    allowed = {str(v) for v in values.values() if isinstance(v, (int, float))} | {"311", "12"}
    return all(number.replace(",", "") in allowed for number in re.findall(r"\d[\d,]*", text))


class QuotaExceeded(Exception):
    """Gemini returned 429. `retry_after` is its suggested wait in seconds (None if not given)."""

    def __init__(self, retry_after: float | None):
        super().__init__(f"Gemini quota reached; retry after {retry_after}s")
        self.retry_after = retry_after


def _retry_after(response: httpx.Response) -> float | None:
    try:
        details = response.json()["error"]["details"]
        delay = next(d["retryDelay"] for d in details if "retryDelay" in d)
        return float(delay.rstrip("s"))
    except (ValueError, KeyError, TypeError, StopIteration):
        return None


def generate(values: dict, timeout: float = 30) -> str | None:
    """One Gemini summary, or None if the call fails or the answer is cut off or uses an unknown number.

    Raises QuotaExceeded on 429, so a caller can wait or stop instead of burning retries.
    """
    try:
        response = httpx.post(
            GEMINI_URL.format(model=settings.gemini_model),
            headers={"x-goog-api-key": settings.gemini_api_key},
            json={"systemInstruction": {"parts": [{"text": INSTRUCTIONS}]},
                  "contents": [{"role": "user", "parts": [{"text": json.dumps(values)}]}],
                  "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024,
                                       "thinkingConfig": {"thinkingBudget": 0}}},
            timeout=timeout,
        )
        if response.status_code == 429:
            raise QuotaExceeded(_retry_after(response))
        response.raise_for_status()
        candidate = response.json()["candidates"][0]
        text = "".join(part.get("text", "") for part in candidate["content"]["parts"]).strip()
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return None
    # A cut-off answer (token limit, safety stop) must never reach the card.
    finished = candidate.get("finishReason") == "STOP" and text.endswith((".", "!", "?"))
    return text if finished and _numbers_ok(text, values) else None


def load_store() -> dict:
    try:
        return json.loads(SUMMARIES_PATH.read_text())
    except (FileNotFoundError, ValueError):
        return {"wards": {}}


def save_store(store: dict) -> None:
    """Atomic write: a reader never sees half a file."""
    with tempfile.NamedTemporaryFile("w", dir=SUMMARIES_PATH.parent, suffix=".tmp", delete=False) as handle:
        json.dump(store, handle, indent=1, sort_keys=True)
        handle.write("\n")
    os.replace(handle.name, SUMMARIES_PATH)
