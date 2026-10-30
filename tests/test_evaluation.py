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


def test_policy_comparison_respects_available_time(model, assets, actions, teams):
    full_window = compare_policies(assets, actions, teams, model, deadline_minutes=120)
    short_window = compare_policies(assets, actions, teams, model, deadline_minutes=35)
    assert short_window[-1]["completed_actions"] <= full_window[-1]["completed_actions"]
    assert short_window[-1]["impact_index"] >= full_window[-1]["impact_index"]
