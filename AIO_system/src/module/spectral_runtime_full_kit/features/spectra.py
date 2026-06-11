from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from labeling.schema import RoiRect


@dataclass(slots=True)
class ClassSignatureSummary:
    class_key: str
    sample_count: int
    mean_spectrum: np.ndarray
    std_spectrum: np.ndarray


def compute_roi_mean_spectrum(data: np.ndarray, roi: RoiRect, mask: np.ndarray | None = None) -> np.ndarray:
    array = np.asarray(data)
    if array.ndim != 3:
        raise ValueError(f"Expected 3D array (frames,width,bands), got shape={array.shape!r}")
    y0 = int(roi.y)
    y1 = int(roi.y + roi.height)
    x0 = int(roi.x)
    x1 = int(roi.x + roi.width)
    if y0 < 0 or x0 < 0 or y1 > int(array.shape[0]) or x1 > int(array.shape[1]):
        raise ValueError(
            f"ROI out of bounds: roi=({roi.x},{roi.y},{roi.width},{roi.height}), shape={array.shape!r}"
        )
    patch = np.asarray(array[y0:y1, x0:x1, :], dtype=np.float32)
    if patch.size == 0:
        raise ValueError("ROI patch is empty.")
    
    # If mask is provided, extract only masked pixels
    if mask is not None:
        mask_patch = np.asarray(mask[y0:y1, x0:x1], dtype=bool)
        if not np.any(mask_patch):
            raise ValueError("No valid pixels in masked ROI region.")
        # Average only pixels where mask is True
        masked_patch = patch[mask_patch, :]
        return np.mean(masked_patch, axis=0)
    
    return np.mean(patch, axis=(0, 1))


def summarize_class_signatures(
    class_samples: Mapping[str, Sequence[np.ndarray]],
    *,
    min_samples: int = 1,
) -> list[ClassSignatureSummary]:
    threshold = max(1, int(min_samples))
    summaries: list[ClassSignatureSummary] = []
    for class_key, samples in class_samples.items():
        vectors: list[np.ndarray] = []
        for sample in samples:
            vector = np.asarray(sample, dtype=np.float32).reshape(-1)
            if vector.size == 0:
                continue
            if not np.all(np.isfinite(vector)):
                continue
            vectors.append(vector)
        if len(vectors) < threshold:
            continue
        stack = np.stack(vectors, axis=0)
        summaries.append(
            ClassSignatureSummary(
                class_key=str(class_key),
                sample_count=int(stack.shape[0]),
                mean_spectrum=np.mean(stack, axis=0),
                std_spectrum=np.std(stack, axis=0),
            )
        )
    return sorted(summaries, key=lambda item: item.class_key)


def spectral_angle_degrees(a: np.ndarray, b: np.ndarray) -> float:
    va = np.asarray(a, dtype=np.float32).reshape(-1)
    vb = np.asarray(b, dtype=np.float32).reshape(-1)
    if va.shape != vb.shape:
        raise ValueError(f"Spectra shape mismatch: {va.shape!r} vs {vb.shape!r}")
    norm_a = float(np.linalg.norm(va))
    norm_b = float(np.linalg.norm(vb))
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    cos_theta = float(np.dot(va, vb) / (norm_a * norm_b))
    cos_theta = float(np.clip(cos_theta, -1.0, 1.0))
    return float(np.degrees(np.arccos(cos_theta)))


def euclidean_distance(a: np.ndarray, b: np.ndarray) -> float:
    va = np.asarray(a, dtype=np.float32).reshape(-1)
    vb = np.asarray(b, dtype=np.float32).reshape(-1)
    if va.shape != vb.shape:
        raise ValueError(f"Spectra shape mismatch: {va.shape!r} vs {vb.shape!r}")
    return float(np.linalg.norm(va - vb))


def bray_curtis_similarity(a: np.ndarray, b: np.ndarray) -> float:
    va = np.asarray(a, dtype=np.float32).reshape(-1)
    vb = np.asarray(b, dtype=np.float32).reshape(-1)
    if va.shape != vb.shape:
        raise ValueError(f"Spectra shape mismatch: {va.shape!r} vs {vb.shape!r}")
    num = float(np.sum(np.abs(va - vb)))
    den = float(np.sum(np.abs(va + vb)))
    if den <= 0.0:
        return 1.0
    distance = num / den
    similarity = 1.0 - distance
    return float(np.clip(similarity, 0.0, 1.0))


def compute_pairwise_separability(
    summaries: Sequence[ClassSignatureSummary],
) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    items = list(summaries)
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            left = items[i]
            right = items[j]
            rows.append(
                {
                    "class_a": left.class_key,
                    "class_b": right.class_key,
                    "sam_deg": spectral_angle_degrees(left.mean_spectrum, right.mean_spectrum),
                    "euclidean": euclidean_distance(left.mean_spectrum, right.mean_spectrum),
                    "bray_curtis_similarity": bray_curtis_similarity(
                        left.mean_spectrum,
                        right.mean_spectrum,
                    ),
                    "samples_a": float(left.sample_count),
                    "samples_b": float(right.sample_count),
                }
            )
    return sorted(rows, key=lambda row: float(row["sam_deg"]))
