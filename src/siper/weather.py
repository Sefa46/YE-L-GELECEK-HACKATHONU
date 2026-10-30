from __future__ import annotations

from .schemas import SourceType, WeatherEvent
from .storage import load_weather


def get_offline_weather_event() -> WeatherEvent:
    event = load_weather()
    if event.source != SourceType.SYNTHETIC_SCENARIO:
        raise ValueError("Çevrimdışı fixture sentetik olarak etiketlenmelidir")
    return event
