from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from features.bands import build_pseudo_rgb_preview, save_preview_png
from labeling import load_class_schema
from runtime.pixel_inference import DEFAULT_CLASS_COLORS, PixelInferenceResult, build_pixel_overlay


UNKNOWN_COLOR = (48, 48, 48)


@dataclass(slots=True)
class LineInferenceArtifacts:
    preview_png: Path
    class_map_png: Path
    overlay_png: Path
    object_overlay_png: Path | None
    class_map_npy: Path
    confidence_map_npy: Path
    legend_json: Path
    class_colors: dict[int, tuple[int, int, int]]

    def to_summary_paths(self) -> dict[str, str]:
        paths = {
            "line_preview_png": str(self.preview_png),
            "line_class_map_png": str(self.class_map_png),
            "line_overlay_png": str(self.overlay_png),
            "line_class_map_npy": str(self.class_map_npy),
            "line_confidence_map_npy": str(self.confidence_map_npy),
            "line_legend_json": str(self.legend_json),
        }
        if self.object_overlay_png is not None:
            paths["line_object_overlay_png"] = str(self.object_overlay_png)
        return paths


def write_line_inference_artifacts(
    *,
    output_dir: Path,
    cube: np.ndarray,
    pixel_result: PixelInferenceResult,
    class_schema_path: Path | None = None,
    overlay_alpha: float = 0.65,
    object_events: Sequence[Mapping[str, object]] | None = None,
) -> LineInferenceArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    preview = build_pseudo_rgb_preview(np.asarray(cube))
    class_colors = resolve_class_color_map(
        class_names=pixel_result.class_names,
        class_schema_path=class_schema_path,
    )
    class_color_image = build_class_color_image(
        class_map=pixel_result.class_map,
        class_colors=class_colors,
        unknown_index=pixel_result.unknown_index,
    )
    overlay = build_pixel_overlay(
        preview=preview,
        class_map=pixel_result.class_map,
        confidence_map=pixel_result.confidence_map,
        alpha=float(overlay_alpha),
        unknown_index=pixel_result.unknown_index,
        class_colors=class_colors,
    )

    preview_png = save_preview_png(preview, output_dir / "line-preview.png")
    class_map_png = save_preview_png(class_color_image, output_dir / "line-class-map.png")
    overlay_png = save_preview_png(overlay, output_dir / "line-overlay.png")
    object_overlay_png = None
    if object_events is not None:
        object_overlay = build_object_box_overlay(
            base_image=overlay,
            object_events=object_events,
            class_names=pixel_result.class_names,
            class_colors=class_colors,
        )
        object_overlay_png = save_preview_png(
            object_overlay,
            output_dir / "line-object-overlay.png",
        )
    class_map_npy = output_dir / "line-class-map.npy"
    confidence_map_npy = output_dir / "line-confidence-map.npy"
    legend_json = output_dir / "line-class-legend.json"
    np.save(class_map_npy, pixel_result.class_map, allow_pickle=False)
    np.save(confidence_map_npy, pixel_result.confidence_map, allow_pickle=False)
    write_class_legend(
        legend_json,
        class_names=pixel_result.class_names,
        class_colors=class_colors,
        unknown_index=pixel_result.unknown_index,
    )
    return LineInferenceArtifacts(
        preview_png=preview_png,
        class_map_png=class_map_png,
        overlay_png=overlay_png,
        object_overlay_png=object_overlay_png,
        class_map_npy=class_map_npy,
        confidence_map_npy=confidence_map_npy,
        legend_json=legend_json,
        class_colors=class_colors,
    )


def build_object_box_overlay(
    *,
    base_image: np.ndarray,
    object_events: Sequence[Mapping[str, object]],
    class_names: Sequence[str],
    class_colors: Mapping[int, tuple[int, int, int]],
) -> np.ndarray:
    image_array = np.asarray(base_image, dtype=np.uint8)
    if image_array.ndim != 3 or image_array.shape[-1] != 3:
        raise ValueError("base_image must be an RGB image with shape (height, width, 3).")

    height, width = int(image_array.shape[0]), int(image_array.shape[1])
    image = Image.fromarray(image_array.copy(), mode="RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    border_width = max(1, min(width, height) // 300)
    color_by_class_name = {
        str(class_name): tuple(
            int(v)
            for v in class_colors.get(
                index,
                DEFAULT_CLASS_COLORS[index % len(DEFAULT_CLASS_COLORS)],
            )
        )
        for index, class_name in enumerate(class_names)
    }

    for event in object_events:
        objects = event.get("objects", [])
        if not isinstance(objects, list):
            continue
        for raw_object in objects:
            if not isinstance(raw_object, Mapping):
                continue
            bbox = _normalize_bbox(raw_object.get("bbox"))
            if bbox is None:
                continue
            x0, y0, box_width, box_height = bbox
            if box_width <= 0 or box_height <= 0:
                continue
            x1 = min(width - 1, max(0, x0 + box_width - 1))
            y1 = min(height - 1, max(0, y0 + box_height - 1))
            x0 = min(width - 1, max(0, x0))
            y0 = min(height - 1, max(0, y0))
            if x1 < x0 or y1 < y0:
                continue
            class_name = str(raw_object.get("class", "unknown"))
            color = color_by_class_name.get(class_name, (255, 255, 255))
            draw.rectangle((x0, y0, x1, y1), outline=color, width=border_width)
            _draw_object_label(
                draw=draw,
                text=_format_object_label(class_name, raw_object.get("confidence")),
                xy=(x0, y0),
                image_size=(width, height),
                color=color,
                font=font,
            )
    return np.asarray(image, dtype=np.uint8)


def _normalize_bbox(value: object) -> tuple[int, int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        return (int(value[0]), int(value[1]), int(value[2]), int(value[3]))
    except (TypeError, ValueError):
        return None


def _format_object_label(class_name: str, confidence: object) -> str:
    try:
        score = float(confidence)
    except (TypeError, ValueError):
        return str(class_name)
    return f"{class_name} {score:.2f}"


def _draw_object_label(
    *,
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    image_size: tuple[int, int],
    color: tuple[int, int, int],
    font: ImageFont.ImageFont,
) -> None:
    width, height = image_size
    if width < 16 or height < 10:
        return
    x, y = xy
    text_width, text_height = _measure_text(draw, text, font)
    label_width = min(width - x, text_width + 4)
    if label_width <= 2:
        return
    label_height = min(height - y, text_height + 3)
    if label_height <= 2:
        return
    y_top = max(0, y - label_height) if y >= label_height else y
    x_right = min(width - 1, x + label_width)
    y_bottom = min(height - 1, y_top + label_height)
    draw.rectangle((x, y_top, x_right, y_bottom), fill=(0, 0, 0), outline=color)
    draw.text((x + 2, y_top + 1), text, fill=color, font=font)


def _measure_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
) -> tuple[int, int]:
    try:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        return int(right - left), int(bottom - top)
    except AttributeError:
        return (max(1, len(text) * 6), 8)


def build_class_color_image(
    *,
    class_map: np.ndarray,
    class_colors: dict[int, tuple[int, int, int]],
    unknown_index: int = -1,
) -> np.ndarray:
    class_map_array = np.asarray(class_map)
    if class_map_array.ndim != 2:
        raise ValueError("class_map must be a 2D array.")
    image = np.zeros((class_map_array.shape[0], class_map_array.shape[1], 3), dtype=np.uint8)
    image[:, :] = np.asarray(UNKNOWN_COLOR, dtype=np.uint8)
    for class_index, color in class_colors.items():
        if int(class_index) == int(unknown_index):
            continue
        image[class_map_array == int(class_index)] = np.asarray(color, dtype=np.uint8)
    return image


def resolve_class_color_map(
    *,
    class_names: list[str],
    class_schema_path: Path | None = None,
) -> dict[int, tuple[int, int, int]]:
    schema_colors = load_schema_class_colors(class_schema_path)
    colors: dict[int, tuple[int, int, int]] = {}
    for index, class_name in enumerate(class_names):
        schema_color = schema_colors.get(str(class_name))
        if schema_color is not None:
            colors[index] = schema_color
            continue
        colors[index] = DEFAULT_CLASS_COLORS[index % len(DEFAULT_CLASS_COLORS)]
    return colors


def load_schema_class_colors(class_schema_path: Path | None) -> dict[str, tuple[int, int, int]]:
    if class_schema_path is None or not class_schema_path.exists():
        return {}
    try:
        classes, _payload = load_class_schema(class_schema_path)
    except Exception:  # noqa: BLE001
        return {}
    return {
        item.class_name: hex_to_rgb(item.color_hex)
        for item in classes
    }


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    text = str(value).strip()
    if text.startswith("#"):
        text = text[1:]
    if len(text) != 6:
        raise ValueError(f"Expected #RRGGBB color, got {value!r}.")
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def write_class_legend(
    path: Path,
    *,
    class_names: list[str],
    class_colors: dict[int, tuple[int, int, int]],
    unknown_index: int,
) -> Path:
    rows: list[dict[str, object]] = []
    for index, class_name in enumerate(class_names):
        color = class_colors.get(index, DEFAULT_CLASS_COLORS[index % len(DEFAULT_CLASS_COLORS)])
        rows.append(
            {
                "class_index": int(index),
                "class_name": str(class_name),
                "color_rgb": [int(color[0]), int(color[1]), int(color[2])],
                "color_hex": "#{:02X}{:02X}{:02X}".format(int(color[0]), int(color[1]), int(color[2])),
            }
        )
    payload = {
        "unknown_index": int(unknown_index),
        "unknown_color_rgb": list(UNKNOWN_COLOR),
        "unknown_color_hex": "#{:02X}{:02X}{:02X}".format(*UNKNOWN_COLOR),
        "classes": rows,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def resolve_project_class_schema_path(*, session_dir: Path, output_root: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    session_dir = Path(session_dir)
    if session_dir.parent.name == "raw":
        candidates.append(session_dir.parent.parent / "labels" / "class_schema.json")
    if output_root is not None:
        output_root = Path(output_root)
        if output_root.name == "reports":
            candidates.append(output_root.parent / "labels" / "class_schema.json")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else None
