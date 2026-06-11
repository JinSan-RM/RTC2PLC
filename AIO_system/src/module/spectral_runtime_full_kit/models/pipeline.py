from __future__ import annotations

import pickle
from dataclasses import asdict
from pathlib import Path

import numpy as np

from models.plsda import PlsdaClassifier, PlsdaConfig
from models.preprocess import FeatureConfig, SpectrumPreprocessor


class PlsdaPipeline:
    def __init__(
        self,
        *,
        feature_config: FeatureConfig | None = None,
        model_config: PlsdaConfig | None = None,
    ) -> None:
        self.feature_config = feature_config or FeatureConfig()
        self.model_config = model_config or PlsdaConfig()
        self.preprocessor: SpectrumPreprocessor | None = None
        self.classifier: PlsdaClassifier | None = None
        self.training_input_kind: str = "raw"

    def fit(self, X: np.ndarray, y: np.ndarray, class_names: list[str]) -> "PlsdaPipeline":
        preprocessor = SpectrumPreprocessor(config=self.feature_config).fit(X, y)
        X_prepared = preprocessor.transform(X)
        classifier = PlsdaClassifier(config=self.model_config).fit(X_prepared, y, class_names=class_names)
        self.preprocessor = preprocessor
        self.classifier = classifier
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        classifier = self._require_classifier()
        X_prepared = self._transform(X)
        return classifier.predict(X_prepared)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        classifier = self._require_classifier()
        X_prepared = self._transform(X)
        return classifier.predict_proba(X_prepared)

    def save(self, path: Path) -> Path:
        classifier = self._require_classifier()
        preprocessor = self._require_preprocessor()
        payload = {
            "version": "plsda-pipeline.v1",
            "feature_config": asdict(self.feature_config),
            "model_config": asdict(self.model_config),
            "training_input_kind": str(getattr(self, "training_input_kind", "raw") or "raw"),
            "preprocessor": preprocessor.to_dict(),
            "classifier": classifier.to_payload(),
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            pickle.dump(payload, handle)
        return path

    @classmethod
    def load(cls, path: Path) -> "PlsdaPipeline":
        with Path(path).open("rb") as handle:
            payload = pickle.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Invalid pipeline payload.")
        if payload.get("version") != "plsda-pipeline.v1":
            raise ValueError(f"Unsupported pipeline payload version: {payload.get('version')}")

        feature_config_payload = payload.get("feature_config", {})
        model_config_payload = payload.get("model_config", {})
        if not isinstance(feature_config_payload, dict) or not isinstance(model_config_payload, dict):
            raise ValueError("Invalid pipeline payload config sections.")

        pipeline = cls(
            feature_config=FeatureConfig(**feature_config_payload),
            model_config=PlsdaConfig(**model_config_payload),
        )
        preprocessor_payload = payload.get("preprocessor", {})
        classifier_payload = payload.get("classifier", {})
        if not isinstance(preprocessor_payload, dict) or not isinstance(classifier_payload, dict):
            raise ValueError("Invalid pipeline payload model sections.")
        pipeline.preprocessor = SpectrumPreprocessor.from_payload(preprocessor_payload)
        pipeline.classifier = PlsdaClassifier.from_payload(classifier_payload)
        pipeline.training_input_kind = str(payload.get("training_input_kind", "raw") or "raw")
        return pipeline

    def _transform(self, X: np.ndarray) -> np.ndarray:
        preprocessor = self._require_preprocessor()
        return preprocessor.transform(X)

    def _require_preprocessor(self) -> SpectrumPreprocessor:
        if self.preprocessor is None:
            raise RuntimeError("Pipeline is not fitted yet (missing preprocessor).")
        return self.preprocessor

    def _require_classifier(self) -> PlsdaClassifier:
        if self.classifier is None:
            raise RuntimeError("Pipeline is not fitted yet (missing classifier).")
        return self.classifier
