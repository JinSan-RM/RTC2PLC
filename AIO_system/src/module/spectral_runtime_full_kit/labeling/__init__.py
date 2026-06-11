"""Runtime-safe labeling exports.

This portable kit intentionally avoids UI-only labeling helpers so importing
`labeling` does not require PySide6.
"""

from labeling.exporter import (
    CLASS_SCHEMA_VERSION,
    LABEL_SCHEMA_VERSION,
    load_class_schema,
    load_label_record,
    save_class_schema,
    save_label_record,
)
from labeling.roi_tools import (
    build_bounded_rectangle_roi,
    build_region_grow_sam_mask,
    paint_brush_disk,
    rasterize_freehand_lasso,
    rasterize_polygon_mask,
    smooth_freehand_points,
)
from labeling.schema import LabelClassDefinition, LabelRecord, RoiRect

__all__ = [
    "CLASS_SCHEMA_VERSION",
    "LABEL_SCHEMA_VERSION",
    "LabelClassDefinition",
    "LabelRecord",
    "RoiRect",
    "build_bounded_rectangle_roi",
    "build_region_grow_sam_mask",
    "load_class_schema",
    "load_label_record",
    "paint_brush_disk",
    "rasterize_freehand_lasso",
    "rasterize_polygon_mask",
    "save_class_schema",
    "save_label_record",
    "smooth_freehand_points",
]
