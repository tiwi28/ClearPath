"""Live barrier-risk forecast for today and the next two days.

Runs the ML pipeline's live model (ml/05_train.py --live) on the exported 311 history
(ml/07_export.py) and an Open-Meteo weather forecast. Features are built exactly as in
ml/04_build_panel.py: history windows end LAG days before the target day because Toronto
publishes 311 data monthly.
"""

import csv
import json
from datetime import date, datetime, timedelta
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import lightgbm as lgb
import numpy as np
from fastapi import HTTPException

from .feeds import Feed

DATA = Path(__file__).parent / "data"
TORONTO = ZoneInfo("America/Toronto")
PEARSON = (43.68, -79.63)  # the airport station the model's weather features were trained on
DAYS_AHEAD = 2
WEATHER_TTL = 3600

_prediction_cache: dict[tuple[date, float], dict] = {}


def today() -> date:
    return datetime.now(TORONTO).date()


@cache
def _history():
    meta = json.loads((DATA / "model_meta.json").read_text())
    cells = json.loads((DATA / "risk_cells.geojson").read_text())["features"]
    index = {feature["properties"]["cell"]: i for i, feature in enumerate(cells)}
    first = date.fromisoformat(meta["first_history_day"])
    span = (date.fromisoformat(meta["reports_through"]) - first).days + 1
    daily = np.zeros((len(cells), span), dtype=np.int32)
    with open(DATA / "cell_counts.csv", newline="") as file:
        for row in csv.DictReader(file):
            daily[index[row["cell"]], (date.fromisoformat(row["day"]) - first).days] += int(row["n"])
    before = np.zeros(len(cells), dtype=np.int32)
    with open(DATA / "cell_totals.csv", newline="") as file:
        for row in csv.DictReader(file):
            before[index[row["cell"]]] = int(row["prior"])
    # cumulative[:, k] = reports before day first + k (k = 0..span)
    cumulative = np.concatenate([np.zeros((len(cells), 1), np.int32), daily.cumsum(axis=1)], axis=1) + before[:, None]
    booster = lgb.Booster(model_file=str(DATA / "risk_model_live.txt"))
    return meta, cells, first, cumulative, booster


def _prior(day: date) -> np.ndarray:
    """Reports before `day` per cell; days after the newest export count as zero reports."""
    _, _, first, cumulative, _ = _history()
    return cumulative[:, min(max((day - first).days, 0), cumulative.shape[1] - 1)]


def _fetch_weather() -> dict[date, dict]:
    response = httpx.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": PEARSON[0], "longitude": PEARSON[1], "timezone": "America/Toronto",
        "daily": "snowfall_sum,temperature_2m_max,temperature_2m_min,precipitation_sum",
        "hourly": "snow_depth", "past_days": 7, "forecast_days": DAYS_AHEAD + 1,
    }, timeout=10)
    response.raise_for_status()
    data = response.json()
    depth: dict[str, list[float]] = {}
    for stamp, value in zip(data["hourly"]["time"], data["hourly"]["snow_depth"]):
        if value is not None:
            depth.setdefault(stamp[:10], []).append(value)
    daily = data["daily"]
    return {date.fromisoformat(day): {
        "snow": daily["snowfall_sum"][i] or 0.0,  # cm, like Environment Canada "Total Snow"
        "snow_ground": 100 * max(depth[day]) if day in depth else np.nan,  # m -> cm
        "tmin": daily["temperature_2m_min"][i], "tmax": daily["temperature_2m_max"][i],
        "precip": daily["precipitation_sum"][i] or 0.0,
    } for i, day in enumerate(daily["time"])}


WEATHER = Feed("open-meteo", _fetch_weather, WEATHER_TTL)


def _weather() -> dict[date, dict]:
    days = WEATHER.get()
    if days is None:
        raise HTTPException(503, detail={"code": "risk_unavailable", "message": "The weather forecast is unavailable, so barrier risk can't be predicted right now."})
    return days


def _weather_features(day: date) -> dict:
    days = _weather()
    window = [days.get(day - timedelta(days=offset)) for offset in range(7)]
    if window[0] is None:
        raise HTTPException(422, detail={"code": "invalid_day", "message": f"Forecasts cover today through {DAYS_AHEAD} days ahead."})
    known = [w for w in window if w]
    freeze_thaw = [int(w["tmin"] < 0 < w["tmax"]) for w in known]
    return {**window[0], "ft": freeze_thaw[0],
            "snow3": sum(w["snow"] for w in known[:3]), "snow7": sum(w["snow"] for w in known),
            "ft3": sum(freeze_thaw[:3])}


def features(day: date) -> dict[str, np.ndarray]:
    meta, cells, _, _, _ = _history()
    lag = meta["lag_days"]
    lag_prior = _prior(day - timedelta(days=lag))
    day_index = (day - date.fromisoformat(meta["panel_start"])).days
    n = len(cells)
    columns = {f"lag_past{w}": lag_prior - _prior(day - timedelta(days=lag + w)) for w in (28, 91, 365)}
    columns["lag_rate_hist"] = lag_prior / (day_index - lag) if day_index > lag else np.full(n, np.nan)
    columns["season_last_year"] = _prior(day - timedelta(days=350)) - _prior(day - timedelta(days=379))
    for name, value in _weather_features(day).items():
        columns[name] = np.full(n, value, dtype=float)
    columns["dow"] = np.full(n, day.weekday())
    columns["month"] = np.full(n, day.month)
    return columns


def predict(day: date | None = None) -> dict:
    """Risk map for `day` (default today): cells with risk, plus provenance for the UI."""
    day = day or today()
    if not today() <= day <= today() + timedelta(days=DAYS_AHEAD):
        raise HTTPException(422, detail={"code": "invalid_day", "message": f"Forecasts cover today through {DAYS_AHEAD} days ahead."})
    meta, cells, _, _, booster = _history()
    _weather()  # refresh the weather cache first; its timestamp is part of the cache key
    key = (day, WEATHER.fetched_at)
    if key not in _prediction_cache:
        columns = features(day)
        matrix = np.column_stack([columns[name] for name in booster.feature_name()]).astype(float)
        risk = booster.predict(matrix)
        through = date.fromisoformat(meta["reports_through"])
        last_year = _prior(through + timedelta(days=1)) - _prior(through - timedelta(days=364))
        warnings = []
        if day - timedelta(days=meta["lag_days"]) > through:
            warnings.append(f"311 history ends {through.isoformat()}; refresh it with ml/08_refresh_311.py for better predictions.")
        _prediction_cache.clear()  # keep only the latest weather run
        _prediction_cache[key] = {
            "date": day.isoformat(),
            "generated_at": datetime.now(TORONTO).isoformat(timespec="minutes"),
            "reports_through": meta["reports_through"],
            "weather": {name: round(float(value), 1) if value == value else None
                        for name, value in _weather_features(day).items()},
            "weather_source": "Open-Meteo forecast, Toronto Pearson",
            "model": {name: meta[name] for name in ("roc_auc", "pr_auc", "top10_capture", "lag_days")},
            "warnings": warnings,
            "features": [{**cell, "properties": {**cell["properties"], "risk": round(float(value), 3),
                                                  "reports_last_year": int(count)}}
                         for cell, value, count in zip(cells, risk, last_year)],
        }
    return _prediction_cache[key]
