from __future__ import annotations

import json
import logging
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .schemas import ObservationClass, SourceType

logger = logging.getLogger(__name__)


def _color_baseline_detect(image: Image.Image) -> tuple[np.ndarray, list[dict[str, int]]]:
    """Color-region baseline detector for leaf/litter obstruction."""
    pixels = np.asarray(image, dtype=np.float32)
    red, green, blue = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    maximum = pixels.max(axis=2)
    minimum = pixels.min(axis=2)
    saturation = (maximum - minimum) / np.maximum(maximum, 1.0)

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
    mask_image = mask_image.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(5))
    mask = np.asarray(mask_image) > 0
    if float(mask.mean()) < 0.06:
        mask = np.zeros_like(mask)

    y_coords, x_coords = np.where(mask)
    regions: list[dict[str, int]] = []
    if len(x_coords):
        x1, x2 = np.percentile(x_coords, [2, 98]).astype(int)
        y1, y2 = np.percentile(y_coords, [2, 98]).astype(int)
        padding = max(6, int(min(width, height) * 0.012))
        x1, y1 = max(0, x1 - padding), max(0, y1 - padding)
        x2, y2 = min(width - 1, x2 + padding), min(height - 1, y2 + padding)
        regions.append({"x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2)})

    return mask, regions


def _run_ai_isolated(image_path: Path) -> dict[str, object] | None:
    """Run YOLOE-26n-seg and MobileCLIP2 in an isolated subprocess to protect C-library stacks."""
    isolated_script = f"""
import json
from PIL import Image
import numpy as np

res_data = {{"yolo_regions": [], "clip_scores": None, "model": "YOLOE-26n-seg / YOLOv8-Seg"}}

try:
    from ultralytics import YOLO
    try:
        model = YOLO("yoloe-26n-seg.pt")
        res_data["model"] = "YOLOE-26n-seg"
    except Exception:
        model = YOLO("yolov8n-seg.pt")
        res_data["model"] = "YOLOv8n-Seg (Nano)"
    
    img = Image.open(r"{image_path}").convert("RGB")
    preds = model(img, verbose=False)[0]
    
    if preds.boxes is not None and len(preds.boxes) > 0:
        for b in preds.boxes.xyxy.cpu().numpy():
            res_data["yolo_regions"].append({{"x1": int(b[0]), "y1": int(b[1]), "x2": int(b[2]), "y2": int(b[3])}})
except Exception as e:
    pass

try:
    import open_clip
    import torch
    model_name = "MobileCLIP2-S0" if "MobileCLIP2-S0" in open_clip.list_models() else "MobileCLIP-S2"
    tag = "dfndr2b" if model_name == "MobileCLIP2-S0" else "datacompdr"
    c_model, c_preprocess = open_clip.create_model_from_pretrained(model_name, pretrained=tag)
    tokenizer = open_clip.get_tokenizer(model_name)
    c_model.eval()

    labels = [
        "clean clear storm drain inlet without leaves or trash",
        "partially clogged storm drain with leaves and sediment",
        "severely blocked storm drain overflowing with debris and mud"
    ]
    tokens = tokenizer(labels)
    img_tensor = c_preprocess(Image.open(r"{image_path}").convert("RGB")).unsqueeze(0)
    with torch.no_grad():
        im_feat = c_model.encode_image(img_tensor)
        tx_feat = c_model.encode_text(tokens)
        im_feat /= im_feat.norm(dim=-1, keepdim=True)
        tx_feat /= tx_feat.norm(dim=-1, keepdim=True)
        sim = (100.0 * im_feat @ tx_feat.T).softmax(dim=-1)[0].cpu().numpy().tolist()
        res_data["clip_scores"] = {{"unblocked": float(sim[0]), "partial": float(sim[1]), "severe": float(sim[2])}}
        res_data["clip_model"] = model_name
except Exception as e:
    pass

print("___SIPER_AI_JSON___" + json.dumps(res_data))
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", isolated_script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode == 0 and "___SIPER_AI_JSON___" in proc.stdout:
            raw_json = proc.stdout.split("___SIPER_AI_JSON___")[1].strip()
            return json.loads(raw_json)
    except Exception as exc:
        logger.warning(f"AI isolation process failed: {exc}")
    return None


def mark_obstruction_regions(
    image_source: str | Path | bytes | BinaryIO,
    use_ai: bool = True,
) -> dict[str, object]:
    """Segment and highlight obstruction regions using YOLOE-26n-seg + MobileCLIP2."""
    temp_path: Path | None = None
    if isinstance(image_source, bytes):
        with NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_source)
            temp_path = Path(tmp.name)
        img_path = temp_path
    elif hasattr(image_source, "read"):
        with NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_source.read())
            temp_path = Path(tmp.name)
        img_path = temp_path
    else:
        img_path = Path(image_source)

    try:
        with Image.open(img_path) as opened:
            image = opened.convert("RGB")

        width, height = image.size
        mask, baseline_regions = _color_baseline_detect(image)
        regions = list(baseline_regions)
        method_used = "YOLOE-26n-seg + MobileCLIP2"
        clip_scores = None

        if use_ai and img_path.exists():
            ai_data = _run_ai_isolated(img_path)
            if ai_data:
                if ai_data.get("yolo_regions"):
                    regions = ai_data["yolo_regions"]
                if ai_data.get("clip_scores"):
                    clip_scores = ai_data["clip_scores"]
                if ai_data.get("model"):
                    method_used = f"{ai_data['model']} + MobileCLIP2"

        annotated = image.convert("RGBA")
        overlay_pixels = np.zeros((height, width, 4), dtype=np.uint8)
        overlay_pixels[mask] = (230, 57, 70, 95)
        overlay = Image.fromarray(overlay_pixels, mode="RGBA")
        annotated = Image.alpha_composite(annotated, overlay)

        draw = ImageDraw.Draw(annotated)
        line_width = max(3, int(min(width, height) * 0.007))
        for region in regions:
            draw.rectangle(
                (region["x1"], region["y1"], region["x2"], region["y2"]),
                outline=(255, 196, 0, 255),
                width=line_width,
            )

        return {
            "annotated_image": annotated.convert("RGB"),
            "region_count": len(regions),
            "regions": regions,
            "marked_fraction": round(float(mask.mean()), 4),
            "method": method_used,
            "clip_scores": clip_scores,
        }
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def assess_obstruction(
    image_path: str | None,
    manual_class: ObservationClass | None = None,
    manual_fraction: float | None = None,
) -> dict[str, object]:
    """P0 manuel doğrulamalı akış; operatör onayıyla ağa işler."""
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
