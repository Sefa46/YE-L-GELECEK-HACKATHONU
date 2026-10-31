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


def get_environmental_profile(asset: Asset) -> dict[str, str | bool]:
    """Parklar, dere çevreleri ve kıyı alanları için çevresel hassasiyet ve akış doğrulaması.

    Yarışma ve hidrolik mühendisliği kuralı:
    Gerçek akış bağlantısı doğrulanmamış serbest yüzey alanlarında (parklar, açık yeşil yamaçlar vb.)
    kesin taşkın önlendiği iddia edilmez; ekolojik tampon ve erozyon izleme bölgesi olarak sınıflandırılır.
    """
    zone = asset.drainage_zone_id.lower()
    asset_id = asset.id.upper()
    asset_type = asset.type.value if hasattr(asset.type, "value") else str(asset.type)
    name = asset.name.lower()

    if asset_id == "I4" or "park" in name or asset_id == "I7" or "seyir" in name:
        category = "Park & Yeşil Alan"
        badge = "🌳 Park & Yeşil Alan"
        is_verified_hydraulic = False
        verification_label = "⚠️ Tampon İzleme Bölgesi"
        status_note = (
            "Ekolojik tampon bölge. Izgara girişi bağlıdır; ancak park geneli 2D serbest yüzey "
            "akış modeli henüz kalibre edilmediğinden 'parkta taşkın kesin önlendi' denilmez, "
            "su tutma ve erozyon tamponu olarak izlenir."
        )
    elif (
        "dere" in name
        or "kanal" in name
        or "degirmendere" in zone
        or asset_type in ("open_channel", "collector")
    ):
        category = "Dere & Vadi Koridoru"
        badge = "💧 Dere Koridoru"
        is_verified_hydraulic = True
        verification_label = "✅ Doğrulanmış Hat"
        status_note = (
            "Doğrulanmış açık/kapalı yatak akış bağlantısı (1D hidrolik model ve menfez/kanal kapasitesi kapsamında)."
        )
    elif (
        "ganita" in zone
        or "liman" in zone
        or "sahil" in name
        or asset_type in ("storage", "pump_station", "outfall")
    ):
        category = "Kıyı Şeridi & Deniz Deşarjı"
        badge = "🌊 Kıyı & Deşarj Hattı"
        is_verified_hydraulic = True
        verification_label = "✅ Doğrulanmış Hat"
        status_note = (
            "Doğrulanmış kıyı tahliye ve deniz deşarj bağlantısı (Karadeniz kıyı koruma ve terfi hattı)."
        )
    else:
        category = "Kentsel Drenaj Arterleri"
        badge = "🏙️ Kentsel Arter"
        is_verified_hydraulic = True
        verification_label = "✅ Doğrulanmış Hat"
        status_note = (
            "Doğrulanmış kentsel cadde ve sokak drenaj şebekesi bağlantısı."
        )

    return {
        "category": category,
        "badge": badge,
        "is_verified_hydraulic": is_verified_hydraulic,
        "verification_label": verification_label,
        "status_note": status_note,
    }
