from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"YAML document at {path} must be a mapping.")
    return payload
