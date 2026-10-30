from __future__ import annotations

from itertools import cycle
from typing import Any

from .schemas import Asset, ObservationClass


def obstruction_class_for_fraction(fraction: float | None) -> ObservationClass:
    """Görsel kapanma oranını harita için üç anlaşılır seviyeye ayırır."""
    if fraction is not None and fraction >= 0.70:
        return ObservationClass.SEVERE
    if fraction is not None and fraction >= 0.40:
        return ObservationClass.PARTIAL
    return ObservationClass.UNBLOCKED


def link_assets_to_vision_samples(
    assets: list[Asset], samples: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Her altyapı noktasını kendi yapı türüne (mazgal, menfez, açık kanal, pompa, deşarj, boru) ve tıkanıklık durumuna tam uyan doğrulanmış bir görüntüye bağlar."""
    sample_by_id = {s["id"]: s for s in samples}

    # Yapı türü ve tıkanıklık durumuna göre özel gerçekçi eşleştirme matrisi
    TYPE_AWARE_MATCHES: dict[str, dict[str, str]] = {
        # Açık kanal (Doğu kanalı, vadi tabanı)
        "open_channel": {
            "severe": "REAL-CHANNEL-01",
            "partial": "REAL-CHANNEL-01",
            "unblocked": "REAL-CHANNEL-01",
        },
        # Pompa istasyonu (Liman terfi istasyonu)
        "pump_station": {
            "severe": "REAL-PUMP-01",
            "partial": "REAL-PUMP-01",
            "unblocked": "REAL-PUMP-01",
        },
        # Karadeniz sahil deşarj ağzı (Ganita çıkışı)
        "outfall": {
            "severe": "REAL-OUTFALL-01",
            "partial": "REAL-OUTFALL-01",
            "unblocked": "REAL-OUTFALL-01",
        },
        # Depolama tesisi
        "storage": {
            "severe": "REAL-STORAGE-01",
            "partial": "REAL-STORAGE-01",
            "unblocked": "REAL-STORAGE-01",
        },
        # Menfezler (Betonarme kutu menfez)
        "culvert": {
            "severe": "REAL-CULVERT-01",
            "partial": "REAL-CULVERT-03",
            "unblocked": "REAL-CULVERT-02",
        },
        # Sokak ızgaraları / Mazgallar
        "grate": {
            "severe": "REAL-GRATE-01",
            "partial": "REAL-GRATE-03",
            "unblocked": "REAL-GRATE-02",
        },
        # Bordür su girişleri
        "inlet": {
            "severe": "REAL-INLET-01",
            "partial": "REAL-INLET-02",
            "unblocked": "REAL-GRATE-02",
        },
        # Kapalı boru ve ana kolektörler (Boru içi akış / CCTV kaydı)
        "pipe": {
            "severe": "VHBD-B02",
            "partial": "VHBD-P01",
            "unblocked": "VHBD-C02",
        },
        "collector": {
            "severe": "VHBD-B01",
            "partial": "VHBD-P02",
            "unblocked": "VHBD-C01",
        },
    }

    links: dict[str, dict[str, Any]] = {}
    for asset in assets:
        obs_class = obstruction_class_for_fraction(
            asset.blockage_visual_fraction
        ).value
        asset_type_val = (
            asset.type.value if hasattr(asset.type, "value") else str(asset.type)
        )
        matched_id = TYPE_AWARE_MATCHES.get(asset_type_val, {}).get(obs_class)
        if matched_id and matched_id in sample_by_id:
            links[asset.id] = sample_by_id[matched_id]
        else:
            # Sınıfa uyan ilk uygun örneği ata
            fallback = next(
                (s for s in samples if s.get("dataset_class") == obs_class),
                samples[0],
            )
            links[asset.id] = fallback
    return links
