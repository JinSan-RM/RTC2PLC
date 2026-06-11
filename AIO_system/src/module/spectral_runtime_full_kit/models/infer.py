from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np

from models.pipeline import PlsdaPipeline
from models.plsda import PlsdaClassifier


def load_model(path: Path) -> PlsdaPipeline | PlsdaClassifier:
    path = Path(path)
    with path.open("rb") as handle:
        payload = pickle.load(handle)

    if isinstance(payload, dict) and payload.get("version") == "plsda-pipeline.v1":
        return PlsdaPipeline.load(path)
    if isinstance(payload, dict):
        return PlsdaClassifier.from_payload(payload)
    if isinstance(payload, PlsdaClassifier):
        return payload
    raise ValueError(f"Unsupported model payload type: {type(payload)}")


def predict(model: PlsdaPipeline | PlsdaClassifier, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    predicted_indices = model.predict(X)
    probabilities = model.predict_proba(X)
    return predicted_indices, probabilities
