from __future__ import annotations

from itertools import combinations

from .hydraulics import ProxyHydraulicModel
from .network import travel_minutes
from .schemas import Action, Assignment, Plan, Team


def _eligible(team: Team, action: Action) -> bool:
    return set(action.required_skills).issubset(team.skills) and set(
        action.required_equipment
    ).issubset(team.equipment)


def assign_portfolio(
    model: ProxyHydraulicModel,
    actions: list[Action],
    teams: list[Team],
    deadline_minutes: int,
    benefit_order: dict[str, float],
) -> list[Assignment] | None:
    team_time = {team.id: 0 for team in teams}
    team_location = {team.id: team.start_asset_id for team in teams}
    assignments: list[Assignment] = []
    for action in sorted(actions, key=lambda item: benefit_order.get(item.id, 0), reverse=True):
        options: list[tuple[int, Team, int, int]] = []
        for team in teams:
            if not _eligible(team, action):
                continue
            travel = travel_minutes(model.graph, team_location[team.id], action.asset_id)
            start = max(team_time[team.id] + travel, action.earliest_start_minute)
            end = start + action.duration_minutes
            if end <= deadline_minutes:
                options.append((end, team, start, travel))
        if not options:
            return None
        end, team, start, travel = min(options, key=lambda item: item[0])
        assignments.append(
            Assignment(
                team_id=team.id,
                action_id=action.id,
                start_minute=start,
                end_minute=end,
                travel_minutes=travel,
            )
        )
        team_time[team.id] = end
        team_location[team.id] = action.asset_id
    return assignments


def optimize_plan(
    model: ProxyHydraulicModel,
    actions: list[Action],
    teams: list[Team],
    deadline_minutes: int = 120,
    max_actions: int = 3,
) -> Plan:
    baseline = model.run()
    single_benefits = {
        action.id: baseline.total_impact_index - model.run([action]).total_impact_index
        for action in actions
    }
    best: tuple[float, list[Action], list[Assignment], float] | None = None
    for size in range(1, min(max_actions, len(actions)) + 1):
        for portfolio in combinations(actions, size):
            assignments = assign_portfolio(
                model, list(portfolio), teams, deadline_minutes, single_benefits
            )
            if assignments is None:
                continue
            impact = model.run(list(portfolio)).total_impact_index
            benefit = baseline.total_impact_index - impact
            finish = max((item.end_minute for item in assignments), default=0)
            candidate = (benefit, list(portfolio), assignments, impact)
            if best is None or (benefit, -finish) > (
                best[0],
                -max(item.end_minute for item in best[2]),
            ):
                best = candidate
    if best is None:
        best = (0.0, [], [], baseline.total_impact_index)
    benefit, selected, assignments, impact = best
    selected_ids = {action.id for action in selected}
    rejected: dict[str, str] = {}
    for action in actions:
        if action.id in selected_ids:
            continue
        if not any(_eligible(team, action) for team in teams):
            rejected[action.id] = "Uygun ekip yetkinliği veya ekipmanı yok"
        else:
            rejected[action.id] = "Süre ve sistem-geneli portföy faydası nedeniyle seçilmedi"
    portfolio_key = "-".join(sorted(selected_ids)) or "NONE"
    return Plan(
        plan_id=f"PLAN-{baseline.scenario_hash}-{portfolio_key}",
        selected_action_ids=sorted(selected_ids),
        assignments=sorted(assignments, key=lambda item: (item.team_id, item.start_minute)),
        rejected=rejected,
        baseline_impact_index=baseline.total_impact_index,
        planned_impact_index=impact,
        simulated_benefit=round(benefit, 4),
        deadline_minutes=deadline_minutes,
    )
