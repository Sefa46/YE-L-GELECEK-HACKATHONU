from siper.risk import asset_risk_scores, intervention_benefits


def test_risk_distinct_from_benefit(model, assets, actions):
    baseline = model.run()
    risks = asset_risk_scores(assets, baseline.node_impact)
    benefits = intervention_benefits(model, actions)
    action_map = {action.id: action for action in actions}
    highest_risk_asset = max(risks, key=risks.get)
    highest_benefit_action = max(benefits, key=benefits.get)
    assert action_map[highest_benefit_action].asset_id != highest_risk_asset
