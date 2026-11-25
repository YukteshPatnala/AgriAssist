"""Image feature extraction for leaf disease classification.

Each image is resized to 128x128, then described by:
  * HOG (histogram of oriented gradients) texture features on the grey image, and
  * HSV colour histograms (hue, saturation, value).
These are classic computer-vision features that are explainable and light enough for a laptop.
"""
from __future__ import annotations

import numpy as np
from PIL import Image
from skimage.color import rgb2hsv
from skimage.feature import hog

IMG_SIZE = 128
COLOR_BINS = 16


def load_rgb(source) -> np.ndarray:
    """Open a path or file-like object and return a 128x128x3 float array in [0, 1]."""
    image = Image.open(source).convert("RGB").resize((IMG_SIZE, IMG_SIZE))
    return np.asarray(image, dtype=np.float64) / 255.0


def extract_features(rgb: np.ndarray) -> np.ndarray:
    grey = rgb.mean(axis=2)
    texture = hog(grey, orientations=9, pixels_per_cell=(16, 16), cells_per_block=(2, 2), feature_vector=True)
    hsv = rgb2hsv(rgb)
    colour = []
    for channel in range(3):
        counts, _ = np.histogram(hsv[..., channel], bins=COLOR_BINS, range=(0.0, 1.0))
        colour.append(counts / counts.sum())
    return np.concatenate([texture, *colour])
