from siper.actions import synergy_delta
from siper.schemas import SourceType


def test_intervention_synergy(model, actions):
    action_map = {action.id: action for action in actions}
    assert synergy_delta(model, action_map["A1"], action_map["A3"]) != 0


def test_no_hydraulics_no_fake_cubic_meters(model):
    result = model.run()
    assert result.overflow_volume_m3 is None
    assert result.source == SourceType.HEURISTIC_ESTIMATE
    assert "NOT HYDRAULICALLY VALIDATED" in result.model_label


def test_simulation_labels(model, event):
    result = model.run()
    assert event.source.value == "synthetic_scenario"
    assert result.source.value == "heuristic_estimate"


def test_scenario_cache_returns_stable_copy(model):
    first = model.run()
    second = model.run()
    assert first == second
    assert first is not second
