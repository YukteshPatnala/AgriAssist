"""Load the trained leaf-disease model and return ranked predictions."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import joblib

from .features import extract_features, load_rgb

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


class DiseaseClassifier:
    def __init__(self, model_path: Path, meta_path: Path) -> None:
        bundle = joblib.load(model_path)
        self.pipeline = bundle["pipeline"]
        self.labels = bundle["labels"]  # folder names such as "Tomato___Early_blight"
        self.info = json.loads(meta_path.read_text(encoding="utf-8"))["labels"]

    def predict(self, image_source, top_k: int = 3) -> list[dict]:
        features = extract_features(load_rgb(image_source)).reshape(1, -1)
        probabilities = self.pipeline.predict_proba(features)[0]
        order = probabilities.argsort()[::-1][:top_k]
        results = []
        for index in order:
            label = self.labels[index]
            details = self.info[label]
            results.append({
                "label": label,
                "crop": details["crop"],
                "condition": details["condition"],
                "healthy": details["healthy"],
                "confidence": round(float(probabilities[index]), 4),
            })
        return results


@lru_cache(maxsize=1)
def get_disease_classifier() -> DiseaseClassifier | None:
    model, meta = MODELS_DIR / "disease_model.joblib", MODELS_DIR / "disease_model_meta.json"
    if not model.exists() or not meta.exists():
        return None
    return DiseaseClassifier(model, meta)
