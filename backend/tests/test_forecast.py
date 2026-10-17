from datetime import date, timedelta

import httpx
import pytest
from fastapi import HTTPException

from app import forecast

TODAY = date(2026, 10, 17)
REAL_PREDICT = forecast.predict  # conftest replaces forecast.predict for API tests


def open_meteo(snow_today=0.0, tmin=-3.0, tmax=2.0, depth_m=0.05):
    days = [(TODAY + timedelta(days=offset)).isoformat() for offset in range(-7, 3)]
    snow = [0.0] * 7 + [snow_today, 0.0, 0.0]
    return {
        "daily": {"time": days, "snowfall_sum": snow, "temperature_2m_max": [tmax] * 10,
                  "temperature_2m_min": [tmin] * 10, "precipitation_sum": [0.0] * 10},
        "hourly": {"time": [f"{day}T07:00" for day in days], "snow_depth": [depth_m] * 10},
    }


@pytest.fixture
def weather(monkeypatch):
    monkeypatch.setattr(forecast, "today", lambda: TODAY)
    forecast.WEATHER.reset()
    forecast._prediction_cache.clear()
    state = {"body": open_meteo(), "calls": 0}

    def get(url, **kwargs):
        state["calls"] += 1
        return httpx.Response(200, json=state["body"], request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", get)
    return state


def test_forecast_scores_every_cell_for_today(weather):
    result = REAL_PREDICT()
    assert result["date"] == "2026-10-17"
    assert result["reports_through"] == "2026-09-30"
    assert len(result["features"]) == 753
    assert all(0 <= feature["properties"]["risk"] <= 1 for feature in result["features"])
    assert result["weather"]["ft"] == 1 and result["weather"]["snow_ground"] == 5.0


def test_snow_raises_predicted_risk(weather):
    weather["body"] = open_meteo(tmin=8.0, tmax=16.0, depth_m=0.0)
    mild = sum(feature["properties"]["risk"] for feature in REAL_PREDICT()["features"])
    forecast.WEATHER.reset()
    weather["body"] = open_meteo(snow_today=15.0, tmin=-5.0, tmax=-1.0, depth_m=0.15)
    snowy = sum(feature["properties"]["risk"] for feature in REAL_PREDICT()["features"])
    assert snowy > mild * 5


def test_weather_is_cached(weather):
    REAL_PREDICT()
    REAL_PREDICT(TODAY + timedelta(days=1))
    assert weather["calls"] == 1


@pytest.mark.parametrize("offset", [-1, 3])
def test_forecast_covers_today_to_two_days_ahead(weather, offset):
    with pytest.raises(HTTPException) as error:
        REAL_PREDICT(TODAY + timedelta(days=offset))
    assert error.value.status_code == 422


def test_weather_failure_is_reported(weather, monkeypatch):
    def down(url, **kwargs):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "get", down)
    with pytest.raises(HTTPException) as error:
        REAL_PREDICT()
    assert error.value.status_code == 503
