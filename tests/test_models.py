"""
Integration tests on the trained models. Skipped when ultralytics is not installed
(CI runs only the fast tests).
"""
from pathlib import Path

import pytest

pytest.importorskip("ultralytics")
pytestmark = pytest.mark.models

from src.detector import Detector  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def leaf():
    return Detector(str(ROOT / "models" / "leaf_best.pt"))


@pytest.fixture(scope="module")
def fruit():
    return Detector(str(ROOT / "models" / "fruit_best.pt"))


def test_class_names_come_from_the_models(leaf, fruit):
    assert len(leaf.class_names) == 9 and "Healthy" in leaf.class_names
    assert len(fruit.class_names) == 8 and "Anthracnose" in fruit.class_names


def test_detections_have_the_documented_shape(leaf):
    dets = leaf.predict_path(str(ROOT / "test_images" / "leaf1.jpg"))
    for d in dets:
        assert set(d) == {"class_id", "class_name", "conf", "bbox"}
        assert 0.25 <= d["conf"] <= 1 and len(d["bbox"]) == 4
        assert d["class_name"] == leaf.class_names[d["class_id"]]
