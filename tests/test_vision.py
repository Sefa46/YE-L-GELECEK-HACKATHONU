from pathlib import Path

from PIL import Image

from siper.schemas import ObservationClass
from siper.storage import load_vision_samples, project_root
from siper.vision import assess_obstruction, mark_obstruction_regions


def test_unknown_blockage_not_automatically_zero():
    result = assess_obstruction(None)
    assert result["class"] == ObservationClass.UNKNOWN
    assert result["visual_fraction"] is None


def test_demo_image_marks_obstruction_region():
    image_path = (
        Path(__file__).parents[1]
        / "data"
        / "fixtures"
        / "demo_images"
        / "grate_severe.jpg"
    )
    result = mark_obstruction_regions(image_path)
    assert result["region_count"] == 1
    assert result["marked_fraction"] > 0.05
    assert result["annotated_image"].size == Image.open(image_path).size


def test_neutral_image_does_not_invent_obstruction(tmp_path):
    image_path = tmp_path / "neutral.png"
    Image.new("RGB", (160, 120), (128, 128, 128)).save(image_path)
    result = mark_obstruction_regions(image_path)
    assert result["region_count"] == 0
    assert result["marked_fraction"] == 0


def test_open_dataset_sample_catalog_is_complete():
    samples = load_vision_samples()
    assert len(samples) >= 15
    assert {sample["dataset_class"] for sample in samples} == {
        "unblocked",
        "partial",
        "severe",
    }
    assert all((project_root() / sample["path"]).is_file() for sample in samples)


def test_open_dataset_clear_and_blocked_samples_are_distinct():
    samples = load_vision_samples()
    clear = next(sample for sample in samples if sample["id"] == "VHBD-C02")
    blocked = next(sample for sample in samples if sample["id"] == "VHBD-B01")
    clear_result = mark_obstruction_regions(project_root() / clear["path"])
    blocked_result = mark_obstruction_regions(project_root() / blocked["path"])
    assert clear_result["region_count"] == 0
    assert blocked_result["region_count"] == 1
    assert blocked_result["marked_fraction"] > clear_result["marked_fraction"]
