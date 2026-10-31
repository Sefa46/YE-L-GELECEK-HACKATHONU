from siper.risk import (
    asset_risk_scores,
    get_environmental_profile,
    intervention_benefits,
)


def test_risk_distinct_from_benefit(model, assets, actions):
    baseline = model.run()
    risks = asset_risk_scores(assets, baseline.node_impact)
    benefits = intervention_benefits(model, actions)
    action_map = {action.id: action for action in actions}
    highest_risk_asset = max(risks, key=risks.get)
    highest_benefit_action = max(benefits, key=benefits.get)
    assert action_map[highest_benefit_action].asset_id != highest_risk_asset


def test_environmental_profile_distinguishes_zones_and_verification(assets):
    asset_map = {asset.id: asset for asset in assets}

    # Park (Meydan Parkı I4) - Serbest yüzey akışı henüz 2D doğrulanmadığından is_verified_hydraulic False olmalı
    park_profile = get_environmental_profile(asset_map["I4"])
    assert park_profile["category"] == "Park & Yeşil Alan"
    assert park_profile["is_verified_hydraulic"] is False

    # Dere / Kanal (Değirmendere / Liman Açık Drenaj CH1) - Doğrulanmış yatak
    stream_profile = get_environmental_profile(asset_map["CH1"])
    assert stream_profile["category"] == "Dere & Vadi Koridoru"
    assert stream_profile["is_verified_hydraulic"] is True

    # Kıyı / Deşarj (Ganita Sahil Menfezi C1) - Doğrulanmış kıyı hattı
    coastal_profile = get_environmental_profile(asset_map["C1"])
    assert coastal_profile["category"] == "Kıyı Şeridi & Deniz Deşarjı"
    assert coastal_profile["is_verified_hydraulic"] is True

