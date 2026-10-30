from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from .schemas import Action, Asset, Team, WeatherEvent

T = TypeVar("T", bound=BaseModel)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_json(name: str):
    path = project_root() / "data" / "fixtures" / name
    return json.loads(path.read_text(encoding="utf-8"))


def load_assets() -> list[Asset]:
    return [Asset.model_validate(item) for item in _read_json("demo_network.json")]


def load_weather() -> WeatherEvent:
    return WeatherEvent.model_validate(_read_json("demo_weather.json"))


def load_actions() -> list[Action]:
    return [Action.model_validate(item) for item in _read_json("actions.json")]


def load_teams() -> list[Team]:
    return [Team.model_validate(item) for item in _read_json("teams.json")]
