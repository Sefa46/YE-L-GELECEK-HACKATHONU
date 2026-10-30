from __future__ import annotations

from .hydraulics import ProxyHydraulicModel
from .schemas import Action, Asset


def asset_risk_scores(assets: list[Asset], baseline_node_impact: dict[str, float]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for asset in assets:
        capacity_deficit = 1.0 - (asset.hydraulic_capacity_factor or 1.0)
        confidence = asset.confidence if asset.confidence is not None else 0.35
        observation_uncertainty = 1.0 - confidence
        # Yerel risk, portföy müdahale faydasından bilinçli olarak ayrıdır.
        score = (
            10.0 * capacity_deficit * asset.criticality_weight
            + 4.0 * (asset.water_level_m or 0.0)
            + 2.0 * observation_uncertainty
        )
        scores[asset.id] = round(score, 4)
    return scores


def intervention_benefits(
    model: ProxyHydraulicModel, actions: list[Action]
) -> dict[str, float]:
    baseline = model.run()
    return {
        action.id: round(baseline.total_impact_index - model.run([action]).total_impact_index, 4)
        for action in actions
    }
