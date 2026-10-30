from siper.optimizer import optimize_plan


def test_team_skills_and_equipment(model, actions, teams):
    plan = optimize_plan(model, actions, teams)
    action_map = {action.id: action for action in actions}
    team_map = {team.id: team for team in teams}
    for assignment in plan.assignments:
        action = action_map[assignment.action_id]
        team = team_map[assignment.team_id]
        assert set(action.required_skills).issubset(team.skills)
        assert set(action.required_equipment).issubset(team.equipment)


def test_deadline_respected(model, actions, teams):
    plan = optimize_plan(model, actions, teams, deadline_minutes=60)
    assert all(item.end_minute <= 60 for item in plan.assignments)


def test_assignment_no_duplicate_tasks(model, actions, teams):
    plan = optimize_plan(model, actions, teams)
    ids = [assignment.action_id for assignment in plan.assignments]
    assert len(ids) == len(set(ids))
