from __future__ import annotations

from .hydraulics import ProxyHydraulicModel
from .optimizer import assign_portfolio, optimize_plan
from .risk import asset_risk_scores, intervention_benefits
from .schemas import Action, Asset, Team


def _policy_result(
    name: str,
    ordered: list[Action],
    model: ProxyHydraulicModel,
    teams: list[Team],
    max_actions: int = 3,
    deadline_minutes: int = 120,
) -> dict[str, object]:
    benefits = intervention_benefits(model, ordered)
    selected: list[Action] = []
    assignments = []
    for action in ordered:
        candidate = selected + [action]
        attempt = assign_portfolio(model, candidate, teams, deadline_minutes, benefits)
        if attempt is not None and len(candidate) <= max_actions:
            selected = candidate
            assignments = attempt
    result = model.run(selected)
    baseline = model.run()
    return {
        "policy": name,
        "action_ids": [action.id for action in selected],
        "impact_index": result.total_impact_index,
        "benefit_index": round(baseline.total_impact_index - result.total_impact_index, 4),
        "completed_actions": len(assignments),
        "constraint_violations": 0,
        "source": result.source.value,
    }


def compare_policies(
    assets: list[Asset],
    actions: list[Action],
    teams: list[Team],
    model: ProxyHydraulicModel,
    deadline_minutes: int = 120,
) -> list[dict[str, object]]:
    baseline = model.run()
    action_asset = {action.id: next(asset for asset in assets if asset.id == action.asset_id) for action in actions}
    blockage_order = sorted(
        actions,
        key=lambda action: action_asset[action.id].blockage_visual_fraction
        if action_asset[action.id].blockage_visual_fraction is not None
        else -1,
        reverse=True,
    )
    risks = asset_risk_scores(assets, baseline.node_impact)
    risk_order = sorted(actions, key=lambda action: risks[action.asset_id], reverse=True)
    optimized = optimize_plan(model, actions, teams, deadline_minutes=deadline_minutes)
    return [
        {
            "policy": "B0 — Müdahale yok",
            "action_ids": [],
            "impact_index": baseline.total_impact_index,
            "benefit_index": 0.0,
            "completed_actions": 0,
            "constraint_violations": 0,
            "source": baseline.source.value,
        },
        _policy_result(
            "B1 — Görünür tıkanıklık",
            blockage_order,
            model,
            teams,
            deadline_minutes=deadline_minutes,
        ),
        _policy_result(
            "B2 — Yerel risk",
            risk_order,
            model,
            teams,
            deadline_minutes=deadline_minutes,
        ),
        {
            "policy": "P — SİPER AI portföyü",
            "action_ids": optimized.selected_action_ids,
            "impact_index": optimized.planned_impact_index,
            "benefit_index": optimized.simulated_benefit,
            "completed_actions": len(optimized.assignments),
            "constraint_violations": 0,
            "source": optimized.source.value,
        },
    ]
