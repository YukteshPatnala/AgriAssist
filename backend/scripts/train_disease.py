"""Train the leaf-disease classifier on PlantVillage images.

Usage (from the backend folder):
    python scripts/train_disease.py --data /path/to/PlantVillage/raw/color --per-class 400

The folder must contain one sub-folder per class, e.g. "Tomato___Early_blight".
Writes models/disease_model.joblib, models/disease_model_meta.json and models/disease_metrics.json.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.ml.features import extract_features, load_rgb  # noqa: E402

# Ten classes: three crops with healthy and diseased leaves.
DEFAULT_CLASSES = [
    "Tomato___Early_blight", "Tomato___Late_blight", "Tomato___Leaf_Mold",
    "Tomato___Septoria_leaf_spot", "Tomato___healthy",
    "Potato___Early_blight", "Potato___Late_blight", "Potato___healthy",
    "Corn_(maize)___Common_rust_", "Corn_(maize)___healthy",
]


def describe(folder_name: str) -> dict:
    crop, _, condition = folder_name.partition("___")
    condition = condition.replace("_", " ").strip()
    healthy = condition.lower() == "healthy"
    crop = crop.replace("_(maize)", " (maize)").replace(",_bell", " (bell)").replace("_", " ")
    return {"crop": crop, "condition": "Healthy" if healthy else condition.title(), "healthy": healthy}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--per-class", type=int, default=400)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    labels = [c for c in DEFAULT_CLASSES if (args.data / c).is_dir()]
    if len(labels) < 2:
        raise SystemExit(f"No class folders found under {args.data}")

    start = time.time()
    X, y = [], []
    for index, label in enumerate(labels):
        files = sorted(p for p in (args.data / label).iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
        random.shuffle(files)
        for path in files[: args.per_class]:
            X.append(extract_features(load_rgb(path)))
            y.append(index)
        print(f"  {label}: {min(len(files), args.per_class)} images", flush=True)
    X, y = np.array(X), np.array(y)
    print(f"Feature matrix: {X.shape}, extracted in {time.time() - start:.0f}s", flush=True)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=args.seed)
    pipeline = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=0.5))
    pipeline.fit(X_train, y_train)

    predictions = pipeline.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    report = classification_report(y_test, predictions, target_names=labels, output_dict=True, zero_division=0)
    print(f"Held-out test accuracy: {accuracy:.4f} on {len(y_test)} images", flush=True)

    models = BACKEND / "models"
    models.mkdir(exist_ok=True)
    joblib.dump({"pipeline": pipeline, "labels": labels}, models / "disease_model.joblib", compress=3)
    (models / "disease_model_meta.json").write_text(
        json.dumps({"labels": {label: describe(label) for label in labels}}, indent=2), encoding="utf-8")
    (models / "disease_metrics.json").write_text(json.dumps({
        "dataset": "PlantVillage (spMohanty/PlantVillage-Dataset, raw/color)",
        "classes": labels,
        "images_per_class_max": args.per_class,
        "train_images": int(len(y_train)),
        "test_images": int(len(y_test)),
        "test_accuracy": round(float(accuracy), 4),
        "per_class": {k: {m: round(float(v), 4) for m, v in val.items() if m in ("precision", "recall", "f1-score", "support")}
                      for k, val in report.items() if k in labels},
        "model": "StandardScaler + LogisticRegression on HOG + HSV histogram features",
        "seed": args.seed,
    }, indent=2), encoding="utf-8")
    print("Saved model and metrics to", models, flush=True)


if __name__ == "__main__":
    main()
