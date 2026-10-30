from siper.evaluation import compare_policies
from siper.weather import get_offline_weather_event


def test_baselines_equal_conditions(model, assets, actions, teams):
    rows = compare_policies(assets, actions, teams, model)
    assert [row["policy"].split(" — ")[0] for row in rows] == ["B0", "B1", "B2", "P"]
    assert all(row["source"] == "heuristic_estimate" for row in rows)
    assert rows[-1]["impact_index"] <= min(row["impact_index"] for row in rows[1:3])


def test_weather_offline():
    event = get_offline_weather_event()
    assert event.hourly_rain_mm
    assert event.source.value == "synthetic_scenario"
