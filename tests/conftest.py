import pytest

from siper.hydraulics import ProxyHydraulicModel
from siper.storage import load_actions, load_assets, load_teams, load_weather


@pytest.fixture
def assets():
    return load_assets()


@pytest.fixture
def actions():
    return load_actions()


@pytest.fixture
def teams():
    return load_teams()


@pytest.fixture
def event():
    return load_weather()


@pytest.fixture
def model(assets, event):
    return ProxyHydraulicModel(assets, event)
