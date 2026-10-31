from pathlib import Path

import pytest

from siper.actions import synergy_delta
from siper.hydraulics import SwmmHydraulicModel, UnsupportedSwmmActionError
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


@pytest.fixture
def swmm_model():
    path = Path(__file__).parents[1] / "data" / "swmm" / "siper_small_network.inp"
    return SwmmHydraulicModel(path)


def test_swmm_baseline_produces_physical_metrics(swmm_model):
    result = swmm_model.run()
    assert result.source == SourceType.HYDRAULIC_SIMULATION
    assert result.overflow_volume_m3 is not None
    assert result.overflow_volume_m3 > 0
    assert result.engine_version == "5.2.4"
    assert result.flow_units == "LPS"
    assert result.max_node_depth_m["C1"] > 0
    assert abs(result.continuity_error_pct or 0) < 5


def test_swmm_intervention_reduces_overflow(swmm_model, actions):
    action_map = {action.id: action for action in actions}
    baseline = swmm_model.run()
    intervention = swmm_model.run([action_map["A3"]])
    assert intervention.overflow_volume_m3 < baseline.overflow_volume_m3
    assert intervention.scenario_hash != baseline.scenario_hash


def test_swmm_unsupported_action_is_not_silently_applied(swmm_model, actions):
    action_map = {action.id: action for action in actions}
    with pytest.raises(UnsupportedSwmmActionError, match="A6"):
        swmm_model.run([action_map["A6"]])


def test_swmm_green_lid_scenario_reduces_runoff(swmm_model):
    baseline = swmm_model.run()
    green_lid = swmm_model.run(green_lid_scenario=True)
    assert green_lid.overflow_volume_m3 is not None
    assert green_lid.overflow_volume_m3 < baseline.overflow_volume_m3
    assert abs(green_lid.continuity_error_pct or 0) < 5

