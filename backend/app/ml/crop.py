"""Crop recommendation: a random forest plus an explanation based on agronomic ranges."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
FEATURES = ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"]
UNITS = {"N": "kg/ha", "P": "kg/ha", "K": "kg/ha", "temperature": "°C", "humidity": "%", "ph": "", "rainfall": "mm"}


class CropRecommender:
    def __init__(self, model_path: Path, ranges_path: Path) -> None:
        bundle = joblib.load(model_path)
        self.model = bundle["model"]
        self.ranges = json.loads(ranges_path.read_text(encoding="utf-8"))

    def recommend(self, values: dict, top_k: int = 3) -> dict:
        row = pd.DataFrame([[float(values[f]) for f in FEATURES]], columns=FEATURES)
        probabilities = self.model.predict_proba(row)[0]
        order = probabilities.argsort()[::-1][:top_k]
        recommendations = []
        for index in order:
            crop = self.model.classes_[index]
            recommendations.append({
                "crop": crop,
                "probability": round(float(probabilities[index]), 4),
                "warnings": self.explain(crop, values),
            })
        return {"recommendations": recommendations, "top_crop": recommendations[0]["crop"]}

    def explain(self, crop: str, values: dict) -> list[str]:
        """Plain-language checks of each input against the ideal range for the crop."""
        notes = []
        for feature in FEATURES:
            low, high = self.ranges[crop][feature]
            value = values[feature]
            unit = UNITS[feature]
            if value < low:
                notes.append(f"{feature} is {value:g}{unit}, below the ideal {low:g}-{high:g}{unit} for {crop}.")
            elif value > high:
                notes.append(f"{feature} is {value:g}{unit}, above the ideal {low:g}-{high:g}{unit} for {crop}.")
        return notes


@lru_cache(maxsize=1)
def get_crop_recommender() -> CropRecommender | None:
    model, ranges = MODELS_DIR / "crop_model.joblib", MODELS_DIR / "crop_ranges.json"
    if not model.exists() or not ranges.exists():
        return None
    return CropRecommender(model, ranges)
