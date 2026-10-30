from __future__ import annotations

import json
from datetime import datetime
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from .schemas import ForecastHour, SourceType, WeatherEvent, WeatherForecast
from .storage import load_weather

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TRABZON_LATITUDE = 41.0027
TRABZON_LONGITUDE = 39.7168
TRABZON_TIMEZONE = "Europe/Istanbul"


class WeatherProviderError(RuntimeError):
    """Canlı meteoroloji sağlayıcısından kullanılabilir yanıt alınamadı."""


def _read_response(response) -> bytes:
    with response:
        return response.read()


def fetch_open_meteo_forecast(
    *,
    latitude: float = TRABZON_LATITUDE,
    longitude: float = TRABZON_LONGITUDE,
    location_name: str = "Trabzon, Ortahisar",
    timeout: float = 6.0,
    now: datetime | None = None,
    opener: Callable = urlopen,
) -> WeatherForecast:
    """Open-Meteo'dan Trabzon için saatlik tahmini alır ve kaynak etiketler."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": (
            "precipitation,precipitation_probability,temperature_2m,"
            "weather_code,wind_speed_10m"
        ),
        "timezone": TRABZON_TIMEZONE,
        "forecast_hours": 48,
    }
    request_url = f"{OPEN_METEO_FORECAST_URL}?{urlencode(params)}"
    try:
        payload = json.loads(_read_response(opener(request_url, timeout=timeout)))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise WeatherProviderError(f"Open-Meteo isteği başarısız: {exc}") from exc

    if payload.get("error"):
        raise WeatherProviderError(str(payload.get("reason", "Open-Meteo API hatası")))

    hourly = payload.get("hourly") or {}
    required_fields = (
        "time",
        "precipitation",
        "precipitation_probability",
        "temperature_2m",
        "weather_code",
        "wind_speed_10m",
    )
    if any(not isinstance(hourly.get(field), list) for field in required_fields):
        raise WeatherProviderError("Open-Meteo yanıtında gerekli saatlik alanlar eksik")

    lengths = {len(hourly[field]) for field in required_fields}
    if len(lengths) != 1 or not lengths or lengths == {0}:
        raise WeatherProviderError("Open-Meteo saatlik alan uzunlukları uyumsuz")

    timezone_name = payload.get("timezone") or TRABZON_TIMEZONE
    try:
        timezone = ZoneInfo(timezone_name)
    except (KeyError, ValueError) as exc:
        raise WeatherProviderError(f"Geçersiz tahmin saat dilimi: {timezone_name}") from exc

    fetched_at = now.astimezone(timezone) if now else datetime.now(timezone)
    current_hour = fetched_at.replace(minute=0, second=0, microsecond=0)
    hours: list[ForecastHour] = []
    try:
        for index, time_value in enumerate(hourly["time"]):
            hour_time = datetime.fromisoformat(time_value).replace(tzinfo=timezone)
            if hour_time < current_hour:
                continue
            hours.append(
                ForecastHour(
                    time=hour_time,
                    precipitation_mm=hourly["precipitation"][index],
                    precipitation_probability_pct=hourly["precipitation_probability"][index],
                    temperature_c=hourly["temperature_2m"][index],
                    weather_code=hourly["weather_code"][index],
                    wind_speed_kmh=hourly["wind_speed_10m"][index],
                )
            )
    except (TypeError, ValueError, IndexError) as exc:
        raise WeatherProviderError(f"Open-Meteo saatlik verisi işlenemedi: {exc}") from exc

    if not hours:
        raise WeatherProviderError("Open-Meteo yanıtında ileri tarihli saat bulunamadı")

    return WeatherForecast(
        provider="Open-Meteo",
        location_name=location_name,
        latitude=float(payload.get("latitude", latitude)),
        longitude=float(payload.get("longitude", longitude)),
        timezone=timezone_name,
        fetched_at=fetched_at,
        hours=hours,
        reliability_note=(
            "Open-Meteo saatlik hava tahminidir; resmî MGM uyarısı veya saha gözlemi değildir."
        ),
    )


def forecast_to_weather_event(
    forecast: WeatherForecast,
    *,
    rain_threshold_mm: float = 0.1,
    event_hours: int = 6,
) -> WeatherEvent | None:
    """Yaklaşan ilk yağış saatini karar modelinin WeatherEvent girdisine dönüştürür."""
    rain_index = next(
        (
            index
            for index, hour in enumerate(forecast.hours)
            if hour.precipitation_mm >= rain_threshold_mm
        ),
        None,
    )
    if rain_index is None:
        return None

    selected_hours = forecast.hours[rain_index : rain_index + event_hours]
    starts_at = selected_hours[0].time
    minutes_until_rain = max(
        1,
        int((starts_at - forecast.fetched_at).total_seconds() // 60),
    )
    return WeatherEvent(
        event_id=f"OPEN-METEO-{forecast.fetched_at:%Y%m%d%H%M}",
        name=f"{forecast.location_name} saatlik yağış tahmini",
        starts_at=starts_at,
        horizon_minutes=min(180, minutes_until_rain),
        hourly_rain_mm=[hour.precipitation_mm for hour in selected_hours],
        scenario_id=f"open_meteo_{starts_at:%Y%m%d%H}",
        source=SourceType.FORECAST,
        reliability_note=forecast.reliability_note,
    )


def next_rain_hour(
    forecast: WeatherForecast, rain_threshold_mm: float = 0.1
) -> ForecastHour | None:
    return next(
        (hour for hour in forecast.hours if hour.precipitation_mm >= rain_threshold_mm),
        None,
    )


def get_offline_weather_event() -> WeatherEvent:
    event = load_weather()
    if event.source != SourceType.SYNTHETIC_SCENARIO:
        raise ValueError("Çevrimdışı fixture sentetik olarak etiketlenmelidir")
    return event
