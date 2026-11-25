"""Train the crop recommendation model.

If data/crop_recommendation.csv exists (the public Kaggle "Crop Recommendation Dataset" with columns
N,P,K,temperature,humidity,ph,rainfall,label), it is used. Otherwise a SYNTHETIC dataset is generated
from the ideal ranges in CROP_RANGES. Synthetic results are for pipeline testing only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.ml.crop import FEATURES  # noqa: E402

# Approximate ideal ranges (min, max) per crop. Verify against local agronomy guidance before real use.
CROP_RANGES = {
    "rice":      {"N": (60, 100), "P": (35, 60), "K": (35, 45), "temperature": (20, 27), "humidity": (80, 85), "ph": (5.5, 7.0), "rainfall": (180, 300)},
    "maize":     {"N": (60, 100), "P": (35, 60), "K": (15, 25), "temperature": (18, 27), "humidity": (55, 75), "ph": (5.8, 7.0), "rainfall": (60, 110)},
    "chickpea":  {"N": (20, 60), "P": (55, 80), "K": (75, 85), "temperature": (17, 21), "humidity": (14, 20), "ph": (7.0, 8.0), "rainfall": (65, 95)},
    "cotton":    {"N": (100, 140), "P": (35, 60), "K": (15, 25), "temperature": (22, 26), "humidity": (75, 85), "ph": (6.0, 8.0), "rainfall": (60, 100)},
    "banana":    {"N": (80, 120), "P": (70, 90), "K": (45, 55), "temperature": (25, 30), "humidity": (75, 85), "ph": (5.5, 6.5), "rainfall": (90, 120)},
    "lentil":    {"N": (10, 40), "P": (60, 80), "K": (15, 25), "temperature": (18, 30), "humidity": (60, 70), "ph": (6.0, 7.5), "rainfall": (35, 60)},
}


def synthetic(samples_per_crop: int = 150, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for crop, ranges in CROP_RANGES.items():
        for _ in range(samples_per_crop):
            row = {f: round(float(rng.uniform(*ranges[f])), 2) for f in FEATURES}
            row["label"] = crop
            rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    data_path = BACKEND / "data" / "crop_recommendation.csv"
    if data_path.exists():
        df, source = pd.read_csv(data_path), f"real CSV: {data_path.name}"
    else:
        df, source = synthetic(), "SYNTHETIC data generated from CROP_RANGES (pipeline test only)"
    print("Data source:", source, "| rows:", len(df), flush=True)

    X, y = df[FEATURES], df["label"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=7)
    model = RandomForestClassifier(n_estimators=200, random_state=7, n_jobs=2)
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    print(f"Held-out accuracy: {accuracy:.4f} on {len(y_test)} rows", flush=True)

    models = BACKEND / "models"
    models.mkdir(exist_ok=True)
    joblib.dump({"model": model}, models / "crop_model.joblib", compress=3)
    ranges = {crop: {f: list(map(float, r[f])) for f in FEATURES} for crop, r in CROP_RANGES.items()}
    (models / "crop_ranges.json").write_text(json.dumps(ranges, indent=2), encoding="utf-8")
    report = classification_report(y_test, predictions, output_dict=True, zero_division=0)
    (models / "crop_metrics.json").write_text(json.dumps({
        "data_source": source,
        "rows": int(len(df)),
        "test_rows": int(len(y_test)),
        "test_accuracy": round(float(accuracy), 4),
        "per_class_f1": {k: round(float(v["f1-score"]), 4) for k, v in report.items() if isinstance(v, dict) and k in CROP_RANGES},
        "model": "RandomForestClassifier(n_estimators=200)",
    }, indent=2), encoding="utf-8")
    print("Saved crop model to", models, flush=True)


if __name__ == "__main__":
    main()
