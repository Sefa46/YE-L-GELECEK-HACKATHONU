import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from siper.schemas import SourceType
from siper.weather import (
    WeatherProviderError,
    fetch_open_meteo_forecast,
    forecast_to_weather_event,
    next_rain_hour,
)


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self.payload


def sample_payload() -> dict:
    return {
        "latitude": 41.0,
        "longitude": 39.75,
        "timezone": "Europe/Istanbul",
        "hourly": {
            "time": ["2026-10-30T14:00", "2026-10-30T15:00", "2026-10-30T16:00"],
            "precipitation": [0.0, 1.4, 0.6],
            "precipitation_probability": [10, 70, 55],
            "temperature_2m": [18.0, 17.2, 16.8],
            "weather_code": [2, 61, 61],
            "wind_speed_10m": [5.0, 7.4, 8.1],
        },
    }


def test_fetch_open_meteo_forecast_parses_and_labels_source():
    requested_urls = []

    def opener(url, timeout):
        requested_urls.append((url, timeout))
        return FakeResponse(sample_payload())

    forecast = fetch_open_meteo_forecast(
        now=datetime(2026, 10, 30, 14, 5, tzinfo=ZoneInfo("Europe/Istanbul")),
        opener=opener,
    )

    assert forecast.source == SourceType.FORECAST
    assert forecast.provider == "Open-Meteo"
    assert len(forecast.hours) == 3
    assert forecast.hours[1].precipitation_probability_pct == 70
    assert "forecast_hours=48" in requested_urls[0][0]


def test_forecast_becomes_weather_event_at_first_rain_hour():
    forecast = fetch_open_meteo_forecast(
        now=datetime(2026, 10, 30, 14, 5, tzinfo=ZoneInfo("Europe/Istanbul")),
        opener=lambda *_args, **_kwargs: FakeResponse(sample_payload()),
    )

    event = forecast_to_weather_event(forecast)

    assert event is not None
    assert event.source == SourceType.FORECAST
    assert event.starts_at.hour == 15
    assert event.hourly_rain_mm == [1.4, 0.6]
    assert next_rain_hour(forecast).time == event.starts_at


def test_forecast_without_rain_does_not_create_event():
    payload = sample_payload()
    payload["hourly"]["precipitation"] = [0.0, 0.0, 0.0]
    forecast = fetch_open_meteo_forecast(
        now=datetime(2026, 10, 30, 14, 5, tzinfo=ZoneInfo("Europe/Istanbul")),
        opener=lambda *_args, **_kwargs: FakeResponse(payload),
    )

    assert forecast_to_weather_event(forecast) is None
    assert next_rain_hour(forecast) is None


def test_invalid_open_meteo_payload_raises_provider_error():
    with pytest.raises(WeatherProviderError, match="gerekli saatlik alanlar eksik"):
        fetch_open_meteo_forecast(
            opener=lambda *_args, **_kwargs: FakeResponse({"hourly": {}})
        )
