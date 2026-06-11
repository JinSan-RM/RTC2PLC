from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_session_dir(output_root: Path, label: str) -> Path:
    ensure_directory(output_root)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session_dir = output_root / f"{timestamp}-{label}"
    suffix = 1
    while session_dir.exists():
        session_dir = output_root / f"{timestamp}-{label}-{suffix:02d}"
        suffix += 1
    session_dir.mkdir(parents=True, exist_ok=False)
    return session_dir
