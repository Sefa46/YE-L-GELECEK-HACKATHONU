from siper.observations import (
    link_assets_to_vision_samples,
    obstruction_class_for_fraction,
)
from siper.schemas import ObservationClass
from siper.storage import load_assets, load_vision_samples


def test_obstruction_thresholds_are_stable():
    assert obstruction_class_for_fraction(0.85) == ObservationClass.SEVERE
    assert obstruction_class_for_fraction(0.70) == ObservationClass.SEVERE
    assert obstruction_class_for_fraction(0.55) == ObservationClass.PARTIAL
    assert obstruction_class_for_fraction(0.0) == ObservationClass.UNBLOCKED
    assert obstruction_class_for_fraction(None) == ObservationClass.UNBLOCKED


def test_every_asset_has_matching_vision_sample():
    assets = load_assets()
    links = link_assets_to_vision_samples(assets, load_vision_samples())

    assert set(links) == {asset.id for asset in assets}
    for asset in assets:
        expected_class = obstruction_class_for_fraction(
            asset.blockage_visual_fraction
        ).value
        assert links[asset.id]["dataset_class"] == expected_class
