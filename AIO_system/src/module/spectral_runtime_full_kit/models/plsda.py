from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.cross_decomposition import PLSRegression
from sklearn.preprocessing import StandardScaler


@dataclass(slots=True)
class PlsdaConfig:
    n_components: int = 8
    use_standard_scaler: bool = True


class PlsdaClassifier:
    def __init__(self, config: PlsdaConfig | None = None) -> None:
        self.config = config or PlsdaConfig()
        self._scaler: StandardScaler | None = None
        self._model: PLSRegression | None = None
        self._class_names: list[str] | None = None
        self._fitted_components: int | None = None

    @property
    def class_names(self) -> list[str]:
        if self._class_names is None:
            raise RuntimeError("Model is not fitted yet.")
        return self._class_names

    @property
    def fitted_components(self) -> int:
        if self._fitted_components is None:
            raise RuntimeError("Model is not fitted yet.")
        return self._fitted_components

    def fit(self, X: np.ndarray, y: np.ndarray, class_names: list[str]) -> "PlsdaClassifier":
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y, dtype=np.int64)
        if X.ndim != 2:
            raise ValueError(f"Expected X to be 2D, got {X.shape}")
        if y.ndim != 1:
            raise ValueError(f"Expected y to be 1D, got {y.shape}")
        if X.shape[0] != y.shape[0]:
            raise ValueError("X and y must have the same number of samples.")
        if len(class_names) < 2:
            raise ValueError("PLS-DA requires at least two classes.")

        Y = one_hot(y, len(class_names))
        if self.config.use_standard_scaler:
            self._scaler = StandardScaler(with_mean=True, with_std=True)
            X_model = self._scaler.fit_transform(X)
        else:
            self._scaler = None
            X_model = X

        max_components = min(X_model.shape[0] - 1, X_model.shape[1], self.config.n_components)
        if max_components < 1:
            raise ValueError("Not enough samples or features to fit PLS-DA.")
        model = PLSRegression(n_components=max_components, scale=False)
        model.fit(X_model, Y)

        self._model = model
        self._class_names = list(class_names)
        self._fitted_components = max_components
        return self

    def decision_function(self, X: np.ndarray) -> np.ndarray:
        model = self._require_model()
        X_eval = np.asarray(X, dtype=np.float32)
        if X_eval.ndim != 2:
            raise ValueError(f"Expected X to be 2D, got {X_eval.shape}")
        if self._scaler is not None:
            X_eval = self._scaler.transform(X_eval)
        scores = model.predict(X_eval)
        return np.asarray(scores, dtype=np.float32)

    def predict(self, X: np.ndarray) -> np.ndarray:
        scores = self.decision_function(X)
        return np.argmax(scores, axis=1).astype(np.int64, copy=False)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        scores = self.decision_function(X)
        return softmax(scores)

    def feature_importance(self, expected_features: int | None = None) -> np.ndarray:
        model = self._require_model()
        coef = np.asarray(model.coef_, dtype=np.float32)
        if coef.ndim == 1:
            importance = np.abs(coef)
        else:
            if expected_features is not None:
                if coef.shape[0] == expected_features:
                    importance = np.linalg.norm(coef, axis=1)
                elif coef.shape[1] == expected_features:
                    importance = np.linalg.norm(coef, axis=0)
                else:
                    feature_axis = 0 if coef.shape[0] >= coef.shape[1] else 1
                    importance = np.linalg.norm(coef, axis=1 - feature_axis)
            else:
                feature_axis = 0 if coef.shape[0] >= coef.shape[1] else 1
                importance = np.linalg.norm(coef, axis=1 - feature_axis)
        return np.nan_to_num(importance, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32, copy=False)

    def save(self, path: Path) -> Path:
        payload = self.to_payload()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            pickle.dump(payload, handle)
        return path

    @classmethod
    def load(cls, path: Path) -> "PlsdaClassifier":
        with Path(path).open("rb") as handle:
            payload = pickle.load(handle)
        return cls.from_payload(payload)

    def to_payload(self) -> dict[str, object]:
        return {
            "version": "plsda-classifier.v1",
            "config": self.config,
            "model": self._model,
            "scaler": self._scaler,
            "class_names": self._class_names,
            "fitted_components": self._fitted_components,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "PlsdaClassifier":
        if not isinstance(payload, dict):
            raise ValueError("Invalid PLS-DA payload.")
        model = cls(config=payload["config"])
        model._model = payload["model"]
        model._scaler = payload["scaler"]
        model._class_names = payload["class_names"]
        model._fitted_components = payload["fitted_components"]
        return model

    def _require_model(self) -> PLSRegression:
        if self._model is None:
            raise RuntimeError("Model is not fitted yet.")
        return self._model


def one_hot(y: np.ndarray, n_classes: int) -> np.ndarray:
    Y = np.zeros((y.shape[0], n_classes), dtype=np.float32)
    Y[np.arange(y.shape[0]), y] = 1.0
    return Y


def softmax(scores: np.ndarray) -> np.ndarray:
    stabilized = scores - np.max(scores, axis=1, keepdims=True)
    exp_scores = np.exp(stabilized)
    denominator = np.sum(exp_scores, axis=1, keepdims=True)
    return exp_scores / denominator
