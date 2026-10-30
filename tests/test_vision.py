from siper.schemas import ObservationClass
from siper.vision import assess_obstruction


def test_unknown_blockage_not_automatically_zero():
    result = assess_obstruction(None)
    assert result["class"] == ObservationClass.UNKNOWN
    assert result["visual_fraction"] is None
