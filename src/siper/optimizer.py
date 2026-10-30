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
    deadline_minutes: int = 720,
    max_actions: int | None = None,
) -> Plan:
    """Afet öncesi tüm kritik görevleri ekiplerin yetkinlik ve rotasına göre planlar."""
    baseline = model.run()
    single_benefits = {
        action.id: baseline.total_impact_index - model.run([action]).total_impact_index
        for action in actions
    }
    
    # Öncelik sırası: Fayda ve ağ hidrolik risk azalımına göre sırala
    ordered_actions = sorted(actions, key=lambda a: single_benefits.get(a.id, 0), reverse=True)
    
    team_time = {team.id: 0 for team in teams}
    team_location = {team.id: team.start_asset_id for team in teams}
    assignments: list[Assignment] = []
    selected_actions: list[Action] = []
    rejected: dict[str, str] = {}

    for action in ordered_actions:
        options: list[tuple[int, Team, int, int]] = []
        for team in teams:
            if not _eligible(team, action):
                continue
            travel = travel_minutes(model.graph, team_location[team.id], action.asset_id)
            start = max(team_time[team.id] + travel, action.earliest_start_minute)
            end = start + action.duration_minutes
            if end <= deadline_minutes:
                options.append((end, team, start, travel))
        
        if options:
            # En erken tamamlayabilecek uygun ekibi seç
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
            selected_actions.append(action)
        else:
            if not any(_eligible(team, action) for team in teams):
                rejected[action.id] = "Uygun ekip yetkinliği veya ekipmanı yok"
            else:
                rejected[action.id] = f"Yağış başlangıcına ({deadline_minutes} dk) kadar süre kısıtı nedeniyle yetişmiyor"

    impact = model.run(selected_actions).total_impact_index
    benefit = max(0.0, baseline.total_impact_index - impact)
    selected_ids = sorted(a.id for a in selected_actions)
    portfolio_key = "-".join(selected_ids) or "NONE"

    return Plan(
        plan_id=f"PLAN-{baseline.scenario_hash}-{portfolio_key}",
        selected_action_ids=selected_ids,
        assignments=sorted(assignments, key=lambda item: (item.team_id, item.start_minute)),
        rejected=rejected,
        baseline_impact_index=baseline.total_impact_index,
        planned_impact_index=impact,
        simulated_benefit=round(benefit, 4),
        deadline_minutes=deadline_minutes,
    )
