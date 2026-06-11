from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.signal import savgol_filter
from sklearn.feature_selection import f_classif


@dataclass(slots=True)
class FeatureConfig:
    edge_bands_low: int = 0
    edge_bands_high: int = 0
    use_savgol: bool = True
    savgol_window_length: int = 11
    savgol_polyorder: int = 2
    derivative_order: int = 0
    use_snv: bool = True
    top_k_bands: int | None = 64
    band_selection_method: str = "f_classif"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class SpectrumPreprocessor:
    def __init__(self, config: FeatureConfig | None = None) -> None:
        self.config = config or FeatureConfig()
        self._fitted = False
        self._trimmed_band_indices: np.ndarray | None = None
        self._selected_relative_indices: np.ndarray | None = None
        self._selected_absolute_indices: np.ndarray | None = None

    @property
    def selected_band_indices(self) -> np.ndarray:
        if self._selected_absolute_indices is None:
            raise RuntimeError("Preprocessor is not fitted yet.")
        return self._selected_absolute_indices

    def fit(self, X: np.ndarray, y: np.ndarray) -> "SpectrumPreprocessor":
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y, dtype=np.int64)
        if X.ndim != 2:
            raise ValueError(f"Expected X to be 2D, got {X.shape}")
        if y.ndim != 1:
            raise ValueError(f"Expected y to be 1D, got {y.shape}")
        if X.shape[0] != y.shape[0]:
            raise ValueError("X and y must have matching sample counts.")

        X_base, band_indices = self._apply_base_transforms(X)
        selected_relative = self._select_bands(X_base, y)
        self._trimmed_band_indices = band_indices
        self._selected_relative_indices = selected_relative
        self._selected_absolute_indices = band_indices[selected_relative]
        self._fitted = True
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("Preprocessor is not fitted yet.")
        X = np.asarray(X, dtype=np.float32)
        if X.ndim != 2:
            raise ValueError(f"Expected X to be 2D, got {X.shape}")
        X_base, _ = self._apply_base_transforms(X)
        if self._selected_relative_indices is None:
            raise RuntimeError("Missing selected band indices.")
        X_selected = X_base[:, self._selected_relative_indices]
        return np.nan_to_num(X_selected, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32, copy=False)

    def fit_transform(self, X: np.ndarray, y: np.ndarray) -> np.ndarray:
        self.fit(X, y)
        return self.transform(X)

    def to_dict(self) -> dict[str, object]:
        return {
            "config": self.config.to_dict(),
            "trimmed_band_indices": (
                self._trimmed_band_indices.astype(int).tolist()
                if self._trimmed_band_indices is not None
                else []
            ),
            "selected_band_indices": (
                self._selected_absolute_indices.astype(int).tolist()
                if self._selected_absolute_indices is not None
                else []
            ),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "SpectrumPreprocessor":
        config_payload = payload.get("config", {})
        if not isinstance(config_payload, dict):
            raise ValueError("Invalid preprocessor payload: missing config mapping.")
        preprocessor = cls(config=FeatureConfig(**config_payload))
        selected = payload.get("selected_band_indices", [])
        trimmed = payload.get("trimmed_band_indices", [])
        if not isinstance(selected, list):
            raise ValueError("Invalid preprocessor payload: selected_band_indices must be a list.")
        if not isinstance(trimmed, list):
            raise ValueError("Invalid preprocessor payload: trimmed_band_indices must be a list.")
        selected_array = np.asarray(selected, dtype=np.int64)
        preprocessor._selected_absolute_indices = selected_array
        if trimmed:
            trimmed_array = np.asarray(trimmed, dtype=np.int64)
        else:
            n_bands = len(selected_array) + preprocessor.config.edge_bands_low + preprocessor.config.edge_bands_high
            trimmed_array = np.arange(
                preprocessor.config.edge_bands_low,
                n_bands - preprocessor.config.edge_bands_high,
                dtype=np.int64,
            )
        preprocessor._trimmed_band_indices = trimmed_array
        position = {int(band): idx for idx, band in enumerate(trimmed_array.tolist())}
        preprocessor._selected_relative_indices = np.asarray(
            [position[int(band)] for band in selected_array.tolist()],
            dtype=np.int64,
        )
        preprocessor._fitted = True
        return preprocessor

    def _apply_base_transforms(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        n_bands = X.shape[1]
        low = max(0, int(self.config.edge_bands_low))
        high = max(0, int(self.config.edge_bands_high))
        if low + high >= n_bands:
            raise ValueError(
                f"edge band trimming is too aggressive: low={low}, high={high}, n_bands={n_bands}"
            )

        band_indices = np.arange(low, n_bands - high, dtype=np.int64)
        X_out = X[:, band_indices].astype(np.float32, copy=False)

        if self.config.use_savgol:
            X_out = self._apply_savgol(X_out)

        if self.config.derivative_order > 0:
            for _ in range(int(self.config.derivative_order)):
                X_out = np.gradient(X_out, axis=1).astype(np.float32, copy=False)

        if self.config.use_snv:
            X_out = self._apply_snv(X_out)
        return X_out, band_indices

    def _apply_savgol(self, X: np.ndarray) -> np.ndarray:
        n_bands = X.shape[1]
        window = int(self.config.savgol_window_length)
        polyorder = int(self.config.savgol_polyorder)

        if window <= 2:
            return X
        if window % 2 == 0:
            window += 1
        if window > n_bands:
            window = n_bands if n_bands % 2 == 1 else n_bands - 1
        if window <= polyorder:
            window = polyorder + 1 if (polyorder + 1) % 2 == 1 else polyorder + 2
            if window > n_bands:
                return X

        return savgol_filter(
            X,
            window_length=window,
            polyorder=polyorder,
            axis=1,
            mode="nearest",
        ).astype(np.float32, copy=False)

    def _apply_snv(self, X: np.ndarray) -> np.ndarray:
        mean = np.mean(X, axis=1, keepdims=True)
        std = np.std(X, axis=1, keepdims=True)
        std_safe = np.where(std < 1e-8, 1.0, std)
        return ((X - mean) / std_safe).astype(np.float32, copy=False)

    def _select_bands(self, X: np.ndarray, y: np.ndarray) -> np.ndarray:
        n_features = X.shape[1]
        top_k = self.config.top_k_bands
        if top_k is None or int(top_k) <= 0 or int(top_k) >= n_features:
            return np.arange(n_features, dtype=np.int64)

        if self.config.band_selection_method != "f_classif":
            raise ValueError(f"Unsupported band selection method: {self.config.band_selection_method}")

        scores, _ = f_classif(X, y)
        scores = np.nan_to_num(scores, nan=0.0, posinf=0.0, neginf=0.0)
        k = int(top_k)
        selected = np.argsort(scores)[::-1][:k]
        selected = np.sort(selected.astype(np.int64, copy=False))
        return selected
