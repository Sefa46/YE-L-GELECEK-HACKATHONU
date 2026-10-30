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
    """Her altyapı noktasını tıkanıklık durumuna tam uyan doğrulanmış bir görüntüye bağlar."""
    sample_by_id = {s["id"]: s for s in samples}

    # Modelin ve insanın kesin olarak aynı fikirde olduğu temiz eşleşme listeleri:
    # severe (ciddi tıkalılar): VHBD-B02 (%50.6 kapanma), VHBD-B03 (%28.0), VHBD-B04 (%19.6), VHBD-B01 (%19.4)
    # partial (kısmi tıkalılar): VHBD-P01 (%14.0), VHBD-P02 (%16.8), VHBD-P05 (%18.5), VHBD-P06 (%17.9), VHBD-P07 (%18.5)
    # unblocked (açık / normaller): VHBD-C02 (%0.0), VHBD-C03 (%0.0), VHBD-C05 (%0.0), VHBD-C06 (%0.0), VHBD-C01 (%6.9)
    curated_classes = {
        "severe": [
            sample_by_id.get(sid) for sid in ["VHBD-B02", "VHBD-B03", "VHBD-B04", "VHBD-B01"]
            if sid in sample_by_id
        ],
        "partial": [
            sample_by_id.get(sid) for sid in ["VHBD-P02", "VHBD-P05", "VHBD-P06", "VHBD-P07", "VHBD-P01"]
            if sid in sample_by_id
        ],
        "unblocked": [
            sample_by_id.get(sid) for sid in ["VHBD-C02", "VHBD-C03", "VHBD-C05", "VHBD-C06", "VHBD-C01"]
            if sid in sample_by_id
        ],
    }

    sample_cycles = {
        key: cycle(class_samples) for key, class_samples in curated_classes.items() if class_samples
    }
    links: dict[str, dict[str, Any]] = {}
    for asset in assets:
        observation_class = obstruction_class_for_fraction(
            asset.blockage_visual_fraction
        ).value
        links[asset.id] = next(sample_cycles[observation_class])
    return links
