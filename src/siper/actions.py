from __future__ import annotations

from itertools import combinations

from .hydraulics import ProxyHydraulicModel
from .schemas import Action


def evaluate_action_sets(
    model: ProxyHydraulicModel,
    actions: list[Action],
    max_size: int = 3,
) -> dict[tuple[str, ...], float]:
    baseline = model.run().total_impact_index
    results: dict[tuple[str, ...], float] = {}
    action_map = {action.id: action for action in actions}
    for size in range(1, min(max_size, len(actions)) + 1):
        for ids in combinations(sorted(action_map), size):
            result = model.run([action_map[action_id] for action_id in ids])
            results[ids] = round(baseline - result.total_impact_index, 4)
    return results


def synergy_delta(model: ProxyHydraulicModel, first: Action, second: Action) -> float:
    baseline = model.run().total_impact_index
    first_benefit = baseline - model.run([first]).total_impact_index
    second_benefit = baseline - model.run([second]).total_impact_index
    combined = baseline - model.run([first, second]).total_impact_index
    return round(combined - (first_benefit + second_benefit), 4)
