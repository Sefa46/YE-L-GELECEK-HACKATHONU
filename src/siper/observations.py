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
    """Her altyapı noktasını aynı tıkanıklık sınıfındaki bir görüntüye bağlar."""
    samples_by_class: dict[str, list[dict[str, Any]]] = {
        observation_class.value: []
        for observation_class in (
            ObservationClass.UNBLOCKED,
            ObservationClass.PARTIAL,
            ObservationClass.SEVERE,
        )
    }
    for sample in samples:
        sample_class = sample.get("dataset_class")
        if sample_class in samples_by_class:
            samples_by_class[sample_class].append(sample)

    missing = [key for key, class_samples in samples_by_class.items() if not class_samples]
    if missing:
        raise ValueError(f"Görüntü sınıfları eksik: {', '.join(missing)}")

    sample_cycles = {
        key: cycle(class_samples) for key, class_samples in samples_by_class.items()
    }
    links: dict[str, dict[str, Any]] = {}
    for asset in assets:
        observation_class = obstruction_class_for_fraction(
            asset.blockage_visual_fraction
        ).value
        links[asset.id] = next(sample_cycles[observation_class])
    return links
