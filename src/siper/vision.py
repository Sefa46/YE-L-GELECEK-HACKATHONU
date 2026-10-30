from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .schemas import ObservationClass, SourceType


def mark_obstruction_regions(
    image_source: str | Path | bytes | BinaryIO,
) -> dict[str, object]:
    """Highlight likely leaf/litter regions for operator review.

    This is a deterministic color-region baseline, not a trained detector. It is
    intentionally kept separate from the operator-confirmed obstruction class.
    """
    if isinstance(image_source, bytes):
        source = BytesIO(image_source)
    else:
        source = image_source
    with Image.open(source) as opened:
        image = opened.convert("RGB")

    pixels = np.asarray(image, dtype=np.float32)
    red, green, blue = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    maximum = pixels.max(axis=2)
    minimum = pixels.min(axis=2)
    saturation = (maximum - minimum) / np.maximum(maximum, 1.0)

    # Wet leaves and common litter in the demo stream are mostly warm, saturated
    # regions. Neutral road/metal pixels are excluded to keep the overlay readable.
    warm_debris = (
        (red > green * 1.02)
        & (green > blue * 0.82)
        & (red > blue * 1.20)
        & (saturation > 0.24)
        & (maximum > 45)
        & (maximum < 245)
    )
    green_debris = (
        (green > red * 1.04)
        & (green > blue * 1.08)
        & (saturation > 0.24)
        & (maximum > 45)
    )
    raw_mask = warm_debris | green_debris

    height, width = raw_mask.shape
    focus = np.zeros_like(raw_mask)
    focus[
        int(height * 0.16) : int(height * 0.84),
        int(width * 0.08) : int(width * 0.92),
    ] = True
    raw_mask &= focus

    mask_image = Image.fromarray((raw_mask * 255).astype(np.uint8), mode="L")
    # Join nearby leaf pixels and remove isolated camera noise.
    mask_image = mask_image.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(5))
    mask = np.asarray(mask_image) > 0
    if float(mask.mean()) < 0.06:
        mask = np.zeros_like(mask)
    y_coords, x_coords = np.where(mask)

    annotated = image.convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_pixels = np.zeros((height, width, 4), dtype=np.uint8)
    overlay_pixels[mask] = (230, 57, 70, 92)
    overlay = Image.fromarray(overlay_pixels, mode="RGBA")
    annotated = Image.alpha_composite(annotated, overlay)

    regions: list[dict[str, int]] = []
    if len(x_coords):
        x1, x2 = np.percentile(x_coords, [2, 98]).astype(int)
        y1, y2 = np.percentile(y_coords, [2, 98]).astype(int)
        padding = max(6, int(min(width, height) * 0.012))
        x1, y1 = max(0, x1 - padding), max(0, y1 - padding)
        x2, y2 = min(width - 1, x2 + padding), min(height - 1, y2 + padding)
        regions.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})
        draw = ImageDraw.Draw(annotated)
        line_width = max(3, int(min(width, height) * 0.007))
        draw.rectangle((x1, y1, x2, y2), outline=(255, 196, 0, 255), width=line_width)

    return {
        "annotated_image": annotated.convert("RGB"),
        "region_count": len(regions),
        "regions": regions,
        "marked_fraction": round(float(mask.mean()), 4),
        "method": "color_region_baseline",
    }


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
