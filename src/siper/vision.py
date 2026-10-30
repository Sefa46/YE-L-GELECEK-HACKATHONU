from __future__ import annotations

from pathlib import Path

from .schemas import ObservationClass, SourceType


def assess_obstruction(
    image_path: str | None,
    manual_class: ObservationClass | None = None,
    manual_fraction: float | None = None,
) -> dict[str, object]:
    """P0 manuel doğrulamalı akış; otomatik model doğruluğu iddia etmez."""
    exists = bool(image_path and Path(image_path).exists())
    if manual_class is None:
        return {
            "class": ObservationClass.UNKNOWN,
            "visual_fraction": None,
            "confidence": 0.0,
            "source": SourceType.OPERATOR_INPUT,
            "image_available": exists,
            "method": "manual_verification_required",
        }
    if manual_fraction is not None and not 0 <= manual_fraction <= 1:
        raise ValueError("Görünür kapanma oranı 0 ile 1 arasında olmalıdır")
    return {
        "class": manual_class,
        "visual_fraction": manual_fraction,
        "confidence": 1.0,
        "source": SourceType.OPERATOR_INPUT,
        "image_available": exists,
        "method": "manual_operator_label",
    }
