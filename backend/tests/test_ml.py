"""Machine-learning checks: crop recommendation, and disease prediction on a real PlantVillage image."""
import pytest

from app.ml.classifier import get_disease_classifier
from app.ml.crop import get_crop_recommender
from conftest import PLANTVILLAGE


def test_crop_recommends_rice_for_rice_conditions():
    result = get_crop_recommender().recommend(
        {"N": 90, "P": 42, "K": 43, "temperature": 23, "humidity": 82, "ph": 6.5, "rainfall": 220})
    assert result["top_crop"] == "rice"
    probs = [r["probability"] for r in result["recommendations"]]
    assert probs == sorted(probs, reverse=True) and sum(probs) <= 1.0 + 1e-6


def test_crop_explains_out_of_range_inputs():
    result = get_crop_recommender().recommend(
        {"N": 10, "P": 10, "K": 200, "temperature": 40, "humidity": 30, "ph": 9, "rainfall": 500}, top_k=1)
    warnings = result["recommendations"][0]["warnings"]
    assert warnings and all("ideal" in w for w in warnings)


def test_disease_model_has_ten_classes_with_readable_names():
    clf = get_disease_classifier()
    assert len(clf.labels) == 10
    info = clf.info["Tomato___Early_blight"]
    assert info == {"crop": "Tomato", "condition": "Early Blight", "healthy": False}


@pytest.mark.skipif(not PLANTVILLAGE.exists(), reason="PlantVillage images not available on this machine")
def test_disease_prediction_on_real_leaf_image():
    folder = PLANTVILLAGE / "Tomato___Late_blight"
    image = sorted(folder.iterdir())[0]
    top = get_disease_classifier().predict(image, top_k=3)
    assert len(top) == 3
    assert top[0]["confidence"] >= top[1]["confidence"]
    assert top[0]["crop"] == "Tomato"          # the crop should be recognised even if the disease is confused
