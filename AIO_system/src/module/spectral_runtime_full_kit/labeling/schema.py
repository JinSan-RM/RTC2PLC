from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import re
from typing import Any, Mapping


def _require_non_empty(name: str, value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{name} must be a non-empty string")
    return cleaned


_HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _normalize_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_color_hex(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("color_hex must be a non-empty string.")
    if not cleaned.startswith("#"):
        cleaned = f"#{cleaned}"
    if not _HEX_COLOR_PATTERN.match(cleaned):
        raise ValueError(f"Invalid color_hex format: {value!r}. Expected #RRGGBB.")
    return cleaned.upper()


@dataclass(slots=True)
class RoiRect:
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        self.x = int(self.x)
        self.y = int(self.y)
        self.width = int(self.width)
        self.height = int(self.height)
        if self.x < 0 or self.y < 0:
            raise ValueError("ROI coordinates must be greater than or equal to 0.")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("ROI width and height must be greater than 0.")

    def to_dict(self) -> dict[str, int]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RoiRect":
        return cls(
            x=int(payload["x"]),
            y=int(payload["y"]),
            width=int(payload["width"]),
            height=int(payload["height"]),
        )

@dataclass(slots=True)
class LabelRecord:
    class_name: str
    sample_id: str
    batch_id: str
    operator: str
    capture_date: str
    lighting_profile: str
    reference_id: str
    class_id: str | None = None
    rois: list[RoiRect] = field(default_factory=list) 
    notes: str | None = None
    session_id: str | None = None
    source_session: str | None = None
    samples: list[dict[str, Any]] = field(default_factory=list) # samples 필드 추가

    def __post_init__(self) -> None:
        self.class_name = _require_non_empty("class_name", self.class_name)
        self.sample_id = _require_non_empty("sample_id", self.sample_id)
        self.batch_id = _require_non_empty("batch_id", self.batch_id)
        self.operator = _require_non_empty("operator", self.operator)
        self.lighting_profile = _require_non_empty("lighting_profile", self.lighting_profile)
        self.reference_id = _require_non_empty("reference_id", self.reference_id)
        self.class_id = _normalize_optional_string(self.class_id)
        if self.class_id is not None:
            self.class_id = _require_non_empty("class_id", self.class_id)
        self.capture_date = _normalize_capture_date(self.capture_date)
        if self.notes is not None:
            self.notes = self.notes.strip() or None
        if self.session_id is not None:
            self.session_id = self.session_id.strip() or None
        if self.source_session is not None:
            self.source_session = self.source_session.strip() or None

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_name": self.class_name,
            "sample_id": self.sample_id,
            "batch_id": self.batch_id,
            "operator": self.operator,
            "capture_date": self.capture_date,
            "lighting_profile": self.lighting_profile,
            "reference_id": self.reference_id,
            "class_id": self.class_id,
            "rois": [roi.to_dict() for roi in self.rois],
            "notes": self.notes,
            "session_id": self.session_id,
            "source_session": self.source_session,
            "samples": self.samples, # 추가
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "LabelRecord":
        raw_rois = payload.get("rois", [])
        if not isinstance(raw_rois, list):
            raise ValueError("rois must be a list of ROI regions.")

        return cls(
            class_name=str(payload["class_name"]),
            sample_id=str(payload["sample_id"]),
            batch_id=str(payload["batch_id"]),
            operator=str(payload["operator"]),
            capture_date=str(payload["capture_date"]),
            lighting_profile=str(payload["lighting_profile"]),
            reference_id=str(payload["reference_id"]),
            class_id=str(payload["class_id"]) if payload.get("class_id") is not None else None,
            rois=[RoiRect.from_mapping(roi_payload) for roi_payload in raw_rois], # 기존 RoiRect에서 RoiRegion으로 변경
            notes=str(payload["notes"]) if payload.get("notes") is not None else None,
            session_id=str(payload["session_id"]) if payload.get("session_id") is not None else None,
            source_session=(
                str(payload["source_session"]) if payload.get("source_session") is not None else None
            ),
            samples=payload.get("samples", []), # samples 필드 추가
        )


@dataclass(slots=True)
class LabelClassDefinition:
    class_id: str
    class_name: str
    color_hex: str = "#00E676"
    alias: str | None = None
    hotkey: str | None = None

    def __post_init__(self) -> None:
        self.class_id = _require_non_empty("class_id", self.class_id)
        self.class_name = _require_non_empty("class_name", self.class_name)
        self.color_hex = _normalize_color_hex(self.color_hex)
        self.alias = _normalize_optional_string(self.alias)
        self.hotkey = _normalize_optional_string(self.hotkey)

    def to_dict(self) -> dict[str, str | None]:
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "color_hex": self.color_hex,
            "alias": self.alias,
            "hotkey": self.hotkey,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "LabelClassDefinition":
        return cls(
            class_id=str(payload["class_id"]),
            class_name=str(payload["class_name"]),
            color_hex=str(payload.get("color_hex", "#00E676")),
            alias=str(payload["alias"]) if payload.get("alias") is not None else None,
            hotkey=str(payload["hotkey"]) if payload.get("hotkey") is not None else None,
        )


def _normalize_capture_date(value: str) -> str:
    raw_value = _require_non_empty("capture_date", value)
    return date.fromisoformat(raw_value).isoformat()
