from __future__ import annotations

import json
import re
from pathlib import Path

from common.paths import ensure_directory
from labeling.schema import RoiRect
from labeling.schema import LabelClassDefinition, LabelRecord


LABEL_SCHEMA_VERSION = "spectral-runtime.label.v1"
CLASS_SCHEMA_VERSION = "spectral-runtime.class-schema.v1"
_INVALID_JSON_ESCAPE_RE = re.compile(r"\\(?![\"\\/bfnrtu])")


def save_label_record(path: Path, record: LabelRecord) -> Path:
    ensure_directory(path.parent)
    payload = {
        "schema_version": LABEL_SCHEMA_VERSION,
        "record": record.to_dict(),
    }

    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return path


def load_label_record(path: Path) -> tuple[LabelRecord, dict[str, object]]:
    payload = _load_label_json_payload(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid label payload in {path}")

    schema_version = payload.get("schema_version")
    if schema_version != LABEL_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported label schema version: {schema_version!r}, expected {LABEL_SCHEMA_VERSION!r}"
        )

    record_payload = payload.get("record")
    if not isinstance(record_payload, dict):
        record = _build_record_from_capture_sample_payload(payload, path)
        payload["record"] = record.to_dict()
        return record, payload

    record = LabelRecord.from_mapping(record_payload)
    return record, payload


def _load_label_json_payload(path: Path) -> object:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        text = path.read_text(encoding="utf-8")
        repaired = _INVALID_JSON_ESCAPE_RE.sub(r"\\\\", text)
        return json.loads(repaired)


def _build_record_from_capture_sample_payload(payload: dict[str, object], path: Path) -> LabelRecord:
    raw_samples = payload.get("samples")
    samples = raw_samples if isinstance(raw_samples, list) else []
    trainable_samples = [
        dict(item)
        for item in samples
        if isinstance(item, dict) and str(item.get("class_name", "") or "").strip()
    ]
    if not trainable_samples:
        raise ValueError("Label payload must include a 'record' mapping or trainable samples.")

    source_session = str(payload.get("source_session_dir", "") or "").strip() or None
    session_id = Path(source_session).name if source_session else path.parent.name
    rois: list[RoiRect] = []
    for item in trainable_samples:
        raw_roi = item.get("roi_source")
        if not isinstance(raw_roi, dict):
            raw_roi = item.get("roi")
        if not isinstance(raw_roi, dict):
            continue
        try:
            rois.append(RoiRect.from_mapping(raw_roi))
        except (KeyError, TypeError, ValueError):
            continue
    if not rois:
        raise ValueError("Label payload trainable samples do not contain valid ROIs.")

    capture_date = _first_non_empty(payload, trainable_samples, "capture_date")
    if not capture_date:
        capture_date = _date_from_session_id(session_id) or "1900-01-01"

    return LabelRecord(
        class_name=_first_non_empty(payload, trainable_samples, "class_name"),
        class_id=_first_non_empty(payload, trainable_samples, "class_id") or None,
        sample_id=_first_non_empty(payload, trainable_samples, "sample_id") or session_id,
        batch_id=_first_non_empty(payload, trainable_samples, "batch_id") or "unknown-batch",
        operator=_first_non_empty(payload, trainable_samples, "operator") or "unknown-operator",
        capture_date=capture_date,
        lighting_profile=(
            _first_non_empty(payload, trainable_samples, "lighting_profile") or "unknown-lighting"
        ),
        reference_id=_first_non_empty(payload, trainable_samples, "reference_id") or "unknown-reference",
        rois=rois,
        notes="legacy-capture-sample-manifest",
        session_id=session_id,
        source_session=source_session,
        samples=trainable_samples,
    )


def _first_non_empty(
    payload: dict[str, object],
    sample_rows: list[dict[str, object]],
    key: str,
) -> str:
    value = str(payload.get(key, "") or "").strip()
    if value:
        return value
    for item in sample_rows:
        value = str(item.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _date_from_session_id(session_id: str) -> str | None:
    match = re.match(r"^(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})T", session_id)
    if match is None:
        return None
    return f"{match.group('year')}-{match.group('month')}-{match.group('day')}"


def save_class_schema(path: Path, classes: list[LabelClassDefinition]) -> Path:
    ensure_directory(path.parent)
    payload = {
        "schema_version": CLASS_SCHEMA_VERSION,
        "classes": [item.to_dict() for item in classes],
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return path


def load_class_schema(path: Path) -> tuple[list[LabelClassDefinition], dict[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid class schema payload in {path}")

    schema_version = payload.get("schema_version")
    if schema_version != CLASS_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported class schema version: {schema_version!r}, expected {CLASS_SCHEMA_VERSION!r}"
        )

    raw_classes = payload.get("classes", [])
    if not isinstance(raw_classes, list):
        raise ValueError("Class schema payload must include a 'classes' list.")
    classes = [LabelClassDefinition.from_mapping(item) for item in raw_classes]
    return classes, payload
