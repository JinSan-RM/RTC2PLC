from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


MODEL_BUNDLE_SCHEMA_VERSION = "spectral-runtime.model-bundle.v1"
MODEL_BUNDLE_MANIFEST_FILENAME = "model_bundle.json"


@dataclass(slots=True)
class BundleFileRef:
    path: str
    sha256: str
    bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "bytes": int(self.bytes),
        }

    @classmethod
    def from_payload(cls, payload: object, *, field_name: str) -> "BundleFileRef":
        if not isinstance(payload, dict):
            raise ValueError(f"{field_name} must be an object.")
        path = str(payload.get("path", "")).strip()
        sha256 = str(payload.get("sha256", "")).strip().lower()
        bytes_value = int(payload.get("bytes", 0))
        if not path:
            raise ValueError(f"{field_name}.path must be non-empty.")
        if not _is_sha256(sha256):
            raise ValueError(f"{field_name}.sha256 must be 64-char lowercase hex.")
        if bytes_value < 0:
            raise ValueError(f"{field_name}.bytes must be >= 0.")
        return cls(path=path, sha256=sha256, bytes=bytes_value)


@dataclass(slots=True)
class CalibrationSideRef:
    kind: str
    path: str
    sha256: str
    manifest: BundleFileRef
    mean: BundleFileRef
    std: BundleFileRef

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "path": self.path,
            "sha256": self.sha256,
            "manifest": self.manifest.to_dict(),
            "mean": self.mean.to_dict(),
            "std": self.std.to_dict(),
        }

    @classmethod
    def from_payload(cls, payload: object, *, side: str) -> "CalibrationSideRef":
        if not isinstance(payload, dict):
            raise ValueError(f"calibration.{side} must be an object.")
        kind = str(payload.get("kind", "")).strip().lower()
        path = str(payload.get("path", "")).strip()
        sha256 = str(payload.get("sha256", "")).strip().lower()
        if kind not in {"dark", "white"}:
            raise ValueError(f"calibration.{side}.kind must be 'dark' or 'white'.")
        expected_kind = side.strip().lower()
        if kind != expected_kind:
            raise ValueError(
                f"calibration.{side}.kind must equal '{expected_kind}', got '{kind}'."
            )
        if not path:
            raise ValueError(f"calibration.{side}.path must be non-empty.")
        if not _is_sha256(sha256):
            raise ValueError(f"calibration.{side}.sha256 must be 64-char lowercase hex.")
        return cls(
            kind=kind,
            path=path,
            sha256=sha256,
            manifest=BundleFileRef.from_payload(
                payload.get("manifest"),
                field_name=f"calibration.{side}.manifest",
            ),
            mean=BundleFileRef.from_payload(
                payload.get("mean"),
                field_name=f"calibration.{side}.mean",
            ),
            std=BundleFileRef.from_payload(
                payload.get("std"),
                field_name=f"calibration.{side}.std",
            ),
        )


@dataclass(slots=True)
class CalibrationRef:
    dark: CalibrationSideRef
    white: CalibrationSideRef

    def to_dict(self) -> dict[str, object]:
        return {
            "dark": self.dark.to_dict(),
            "white": self.white.to_dict(),
        }

    @classmethod
    def from_payload(cls, payload: object) -> "CalibrationRef":
        if not isinstance(payload, dict):
            raise ValueError("calibration must be an object.")
        return cls(
            dark=CalibrationSideRef.from_payload(payload.get("dark"), side="dark"),
            white=CalibrationSideRef.from_payload(payload.get("white"), side="white"),
        )


@dataclass(slots=True)
class ModelBundleManifest:
    schema_version: str
    created_at_utc: str
    bundle_id: str
    model: BundleFileRef
    calibration: CalibrationRef
    runtime_params: dict[str, object]
    training_metadata: dict[str, object]
    source: dict[str, str]
    notes: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "created_at_utc": self.created_at_utc,
            "bundle_id": self.bundle_id,
            "model": self.model.to_dict(),
            "calibration": self.calibration.to_dict(),
            "runtime_params": dict(self.runtime_params),
            "training_metadata": dict(self.training_metadata),
            "source": dict(self.source),
        }
        if self.notes:
            payload["notes"] = self.notes
        return payload

    @classmethod
    def from_payload(cls, payload: object) -> "ModelBundleManifest":
        if not isinstance(payload, dict):
            raise ValueError("bundle manifest must be an object.")
        schema_version = str(payload.get("schema_version", "")).strip()
        created_at_utc = str(payload.get("created_at_utc", "")).strip()
        bundle_id = str(payload.get("bundle_id", "")).strip()
        runtime_params = payload.get("runtime_params", {})
        training_metadata = payload.get("training_metadata", {})
        source = payload.get("source", {})
        notes_value = payload.get("notes")
        if schema_version != MODEL_BUNDLE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version={schema_version!r} "
                f"(expected {MODEL_BUNDLE_SCHEMA_VERSION!r})"
            )
        if not created_at_utc:
            raise ValueError("created_at_utc must be non-empty.")
        if not bundle_id:
            raise ValueError("bundle_id must be non-empty.")
        if not isinstance(runtime_params, dict):
            raise ValueError("runtime_params must be an object.")
        if not isinstance(training_metadata, dict):
            raise ValueError("training_metadata must be an object.")
        if not isinstance(source, dict):
            raise ValueError("source must be an object.")
        normalized_source = {
            str(key): str(value)
            for key, value in source.items()
            if str(key).strip() and str(value).strip()
        }
        notes = str(notes_value).strip() if notes_value is not None else None
        if notes == "":
            notes = None

        return cls(
            schema_version=schema_version,
            created_at_utc=created_at_utc,
            bundle_id=bundle_id,
            model=BundleFileRef.from_payload(payload.get("model"), field_name="model"),
            calibration=CalibrationRef.from_payload(payload.get("calibration")),
            runtime_params=dict(runtime_params),
            training_metadata=dict(training_metadata),
            source=normalized_source,
            notes=notes,
        )

    @classmethod
    def create(
        cls,
        *,
        bundle_id: str,
        model: BundleFileRef,
        calibration: CalibrationRef,
        runtime_params: dict[str, object],
        training_metadata: dict[str, object],
        source: dict[str, str],
        notes: str | None = None,
    ) -> "ModelBundleManifest":
        created_at_utc = datetime.now(timezone.utc).isoformat()
        return cls(
            schema_version=MODEL_BUNDLE_SCHEMA_VERSION,
            created_at_utc=created_at_utc,
            bundle_id=bundle_id,
            model=model,
            calibration=calibration,
            runtime_params=dict(runtime_params),
            training_metadata=dict(training_metadata),
            source=dict(source),
            notes=notes,
        )


@dataclass(slots=True)
class BundleValidationReport:
    ok: bool
    errors: list[str]
    warnings: list[str]


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def combine_sha256(items: list[str]) -> str:
    hasher = hashlib.sha256()
    for item in items:
        hasher.update(str(item).encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def make_bundle_file_ref(path: Path, *, relative_to: Path) -> BundleFileRef:
    resolved_path = Path(path).resolve()
    base = Path(relative_to).resolve()
    try:
        relative = resolved_path.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"path {resolved_path} must be under bundle root {base}") from exc
    return BundleFileRef(
        path=str(relative).replace("\\", "/"),
        sha256=compute_sha256(resolved_path),
        bytes=int(resolved_path.stat().st_size),
    )


def bundle_manifest_path(bundle_dir: Path) -> Path:
    return Path(bundle_dir) / MODEL_BUNDLE_MANIFEST_FILENAME


def write_bundle_manifest(bundle_dir: Path, manifest: ModelBundleManifest) -> Path:
    path = bundle_manifest_path(bundle_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(manifest.to_dict(), handle, indent=2)
    return path


def load_bundle_manifest(bundle_dir: Path) -> ModelBundleManifest:
    path = bundle_manifest_path(bundle_dir)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return ModelBundleManifest.from_payload(payload)


def validate_bundle(
    *,
    bundle_dir: Path,
    manifest: ModelBundleManifest | None = None,
    verify_hashes: bool = True,
) -> BundleValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    root = Path(bundle_dir)
    try:
        loaded = manifest or load_bundle_manifest(root)
    except Exception as exc:  # noqa: BLE001
        return BundleValidationReport(ok=False, errors=[f"manifest load failed: {exc}"], warnings=[])

    if loaded.schema_version != MODEL_BUNDLE_SCHEMA_VERSION:
        errors.append(
            f"schema_version mismatch: {loaded.schema_version!r} "
            f"!= {MODEL_BUNDLE_SCHEMA_VERSION!r}"
        )

    _validate_runtime_params(loaded.runtime_params, errors=errors, warnings=warnings)
    _validate_training_metadata(loaded.training_metadata, errors=errors, warnings=warnings)
    _validate_calibration_side_digest(loaded=loaded, errors=errors)
    _validate_reference_pair_shape(loaded=loaded, root=root, errors=errors, warnings=warnings)
    _validate_reference_manifest_kind(loaded=loaded, root=root, errors=errors, warnings=warnings)
    _validate_file_ref(loaded.model, root=root, verify_hashes=verify_hashes, errors=errors)
    _validate_file_ref(loaded.calibration.dark.manifest, root=root, verify_hashes=verify_hashes, errors=errors)
    _validate_file_ref(loaded.calibration.dark.mean, root=root, verify_hashes=verify_hashes, errors=errors)
    _validate_file_ref(loaded.calibration.dark.std, root=root, verify_hashes=verify_hashes, errors=errors)
    _validate_file_ref(loaded.calibration.white.manifest, root=root, verify_hashes=verify_hashes, errors=errors)
    _validate_file_ref(loaded.calibration.white.mean, root=root, verify_hashes=verify_hashes, errors=errors)
    _validate_file_ref(loaded.calibration.white.std, root=root, verify_hashes=verify_hashes, errors=errors)

    return BundleValidationReport(ok=len(errors) == 0, errors=errors, warnings=warnings)


def _validate_runtime_params(
    runtime_params: dict[str, object],
    *,
    errors: list[str],
    warnings: list[str],
) -> None:
    required_fields = (
        "threshold",
        "min_area",
        "connectivity",
        "window_size",
        "stride",
    )
    for field in required_fields:
        if field not in runtime_params:
            errors.append(f"runtime_params.{field} is required.")

    threshold = _as_float(runtime_params.get("threshold"), default=0.5)
    if threshold < 0.0 or threshold > 1.0:
        errors.append(f"runtime_params.threshold must be in [0,1], got {threshold}.")
    connectivity = _as_int(runtime_params.get("connectivity"), default=8)
    if connectivity not in (4, 8):
        errors.append(
            f"runtime_params.connectivity must be 4 or 8, got {connectivity}."
        )
    min_area = _as_int(runtime_params.get("min_area"), default=1)
    if min_area < 1:
        errors.append(f"runtime_params.min_area must be >= 1, got {min_area}.")
    min_class_fraction = _as_float(runtime_params.get("min_class_fraction"), default=0.0)
    if min_class_fraction < 0.0 or min_class_fraction > 1.0:
        errors.append(
            "runtime_params.min_class_fraction must be in [0,1], "
            f"got {min_class_fraction}."
        )
    object_confidence_threshold = _as_float(
        runtime_params.get("object_confidence_threshold"),
        default=0.0,
    )
    if object_confidence_threshold < 0.0 or object_confidence_threshold > 1.0:
        errors.append(
            "runtime_params.object_confidence_threshold must be in [0,1], "
            f"got {object_confidence_threshold}."
        )
    min_bbox_width = _as_int(runtime_params.get("min_bbox_width"), default=1)
    min_bbox_height = _as_int(runtime_params.get("min_bbox_height"), default=1)
    if min_bbox_width < 1:
        errors.append(f"runtime_params.min_bbox_width must be >= 1, got {min_bbox_width}.")
    if min_bbox_height < 1:
        errors.append(f"runtime_params.min_bbox_height must be >= 1, got {min_bbox_height}.")
    max_bbox_aspect_ratio = runtime_params.get("max_bbox_aspect_ratio")
    if max_bbox_aspect_ratio is not None and _as_float(max_bbox_aspect_ratio, default=0.0) < 1.0:
        errors.append("runtime_params.max_bbox_aspect_ratio must be >= 1 when provided.")
    suppress_iou_threshold = runtime_params.get("suppress_iou_threshold")
    if suppress_iou_threshold is not None:
        parsed_iou = _as_float(suppress_iou_threshold, default=0.0)
        if parsed_iou < 0.0 or parsed_iou > 1.0:
            errors.append("runtime_params.suppress_iou_threshold must be in [0,1] when provided.")
    suppress_containment_threshold = runtime_params.get("suppress_containment_threshold")
    if suppress_containment_threshold is not None:
        parsed_containment = _as_float(suppress_containment_threshold, default=0.0)
        if parsed_containment < 0.0 or parsed_containment > 1.0:
            errors.append("runtime_params.suppress_containment_threshold must be in [0,1] when provided.")
    window_size = _as_int(runtime_params.get("window_size"), default=1)
    stride = _as_int(runtime_params.get("stride"), default=1)
    if window_size < 1:
        errors.append(f"runtime_params.window_size must be >= 1, got {window_size}.")
    if stride < 1:
        errors.append(f"runtime_params.stride must be >= 1, got {stride}.")
    if stride > window_size:
        warnings.append(
            "runtime_params.stride is greater than window_size; windows will not overlap."
        )


def _validate_training_metadata(
    training_metadata: dict[str, object],
    *,
    errors: list[str],
    warnings: list[str],
) -> None:
    del warnings
    input_kind = str(
        training_metadata.get("model_input_kind", training_metadata.get("input_kind", "raw"))
        or "raw"
    ).strip().lower()
    if input_kind not in {"raw", "reflectance", "absorbance"}:
        errors.append(
            "training_metadata.model_input_kind must be one of raw, reflectance, absorbance; "
            f"got {input_kind!r}."
        )


def _validate_calibration_side_digest(
    *,
    loaded: ModelBundleManifest,
    errors: list[str],
) -> None:
    for side_name, side in (("dark", loaded.calibration.dark), ("white", loaded.calibration.white)):
        expected = side.sha256
        actual = combine_sha256(
            [
                side.manifest.sha256,
                side.mean.sha256,
                side.std.sha256,
            ]
        )
        if actual != expected:
            errors.append(
                f"calibration.{side_name}.sha256 mismatch: expected={expected}, actual={actual}"
            )


def _validate_reference_pair_shape(
    *,
    loaded: ModelBundleManifest,
    root: Path,
    errors: list[str],
    warnings: list[str],
) -> None:
    dark_path = _resolve_member_path(
        root=root,
        relative_path=loaded.calibration.dark.mean.path,
        errors=errors,
        field_name="calibration.dark.mean.path",
    )
    white_path = _resolve_member_path(
        root=root,
        relative_path=loaded.calibration.white.mean.path,
        errors=errors,
        field_name="calibration.white.mean.path",
    )
    if dark_path is None or white_path is None:
        return
    if not dark_path.exists() or not white_path.exists():
        return
    try:
        dark = np.load(dark_path, allow_pickle=False)
        white = np.load(white_path, allow_pickle=False)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"failed to load reference arrays for shape check: {exc}")
        return
    if dark.ndim != 2:
        errors.append(f"dark mean must be 2D, got shape={dark.shape!r}")
    if white.ndim != 2:
        errors.append(f"white mean must be 2D, got shape={white.shape!r}")
    if dark.shape != white.shape:
        errors.append(
            f"dark/white mean shape mismatch: dark={dark.shape!r}, white={white.shape!r}"
        )
    training_band_count = loaded.training_metadata.get("input_band_count")
    if training_band_count is None:
        return
    expected = _as_int(training_band_count, default=-1)
    if expected > 0 and dark.ndim == 2 and dark.shape[0] != expected:
        warnings.append(
            f"training input_band_count={expected} but reference band_count={dark.shape[0]}"
        )


def _validate_reference_manifest_kind(
    *,
    loaded: ModelBundleManifest,
    root: Path,
    errors: list[str],
    warnings: list[str],
) -> None:
    del warnings
    sides = (
        ("dark", loaded.calibration.dark.manifest.path),
        ("white", loaded.calibration.white.manifest.path),
    )
    for expected_kind, rel_path in sides:
        path = _resolve_member_path(
            root=root,
            relative_path=rel_path,
            errors=errors,
            field_name=f"calibration.{expected_kind}.manifest.path",
        )
        if path is None:
            continue
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"failed to parse {expected_kind} manifest: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"{expected_kind} manifest must be a JSON object.")
            continue
        kind = str(payload.get("kind", "")).strip().lower()
        if kind != expected_kind:
            errors.append(
                f"{expected_kind} manifest kind mismatch: expected {expected_kind!r}, got {kind!r}"
            )


def _validate_file_ref(
    ref: BundleFileRef,
    *,
    root: Path,
    verify_hashes: bool,
    errors: list[str],
) -> None:
    path = _resolve_member_path(
        root=root,
        relative_path=ref.path,
        errors=errors,
        field_name=f"file_ref({ref.path})",
    )
    if path is None:
        return
    if not path.exists():
        errors.append(f"missing file: {ref.path}")
        return
    if not path.is_file():
        errors.append(f"not a file: {ref.path}")
        return
    actual_size = int(path.stat().st_size)
    if actual_size != int(ref.bytes):
        errors.append(
            f"size mismatch for {ref.path}: expected={ref.bytes}, actual={actual_size}"
        )
    if verify_hashes:
        actual_hash = compute_sha256(path)
        if actual_hash != ref.sha256:
            errors.append(
                f"sha256 mismatch for {ref.path}: expected={ref.sha256}, actual={actual_hash}"
            )


def _as_float(value: object, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_int(value: object, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    return all(ch in "0123456789abcdef" for ch in value)


def _resolve_member_path(
    *,
    root: Path,
    relative_path: str,
    errors: list[str],
    field_name: str,
) -> Path | None:
    root_resolved = root.resolve()
    candidate = (root_resolved / str(relative_path)).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        errors.append(
            f"{field_name} escapes bundle root: {relative_path!r} (root={root_resolved})"
        )
        return None
    return candidate
