from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any


ACK_ACTION_ACK = "ack"
ACK_ACTION_UPDATE = "update"
ACK_ACTION_CANCEL = "cancel"
ACK_ACTIONS = {ACK_ACTION_ACK, ACK_ACTION_UPDATE, ACK_ACTION_CANCEL}
DEFAULT_OPERATOR_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,31}$"


def load_ack_records(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def build_ack_state(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    state: dict[str, dict[str, object]] = {}
    for record in records:
        key = ack_record_key(record)
        if not key:
            continue
        action = str(record.get("action", ACK_ACTION_ACK)).strip().lower()
        if action == ACK_ACTION_CANCEL:
            state.pop(key, None)
            continue
        state[key] = record
    return state


def append_ack_record(
    path: Path,
    *,
    payload: dict[str, Any],
    default_session_id: str | None = None,
    operator_id_pattern: str = DEFAULT_OPERATOR_ID_PATTERN,
) -> dict[str, object]:
    record = normalize_ack_record(
        payload=payload,
        default_session_id=default_session_id,
        operator_id_pattern=operator_id_pattern,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False))
        handle.write("\n")
    return record


def normalize_ack_record(
    *,
    payload: dict[str, Any],
    default_session_id: str | None,
    operator_id_pattern: str = DEFAULT_OPERATOR_ID_PATTERN,
) -> dict[str, object]:
    action = str(payload.get("action", ACK_ACTION_ACK)).strip().lower() or ACK_ACTION_ACK
    if action not in ACK_ACTIONS:
        raise ValueError(f"unsupported ack action: {action}")

    by = str(payload.get("by", "")).strip()
    if not by:
        raise ValueError("ack payload must include non-empty 'by'.")
    if not re.match(operator_id_pattern, by):
        raise ValueError(f"operator id does not match required pattern: {operator_id_pattern}")

    try:
        window_index = int(payload.get("window_index"))
    except (TypeError, ValueError) as exc:
        raise ValueError("ack payload must include integer 'window_index'.") from exc

    timestamp = _to_int(payload.get("timestamp"), default=0)
    timestamp_iso = str(payload.get("timestamp_iso", "") or "")
    status = str(payload.get("status", "") or "")
    note = str(payload.get("note", "") or "")
    status_at_ack = str(payload.get("status_at_ack", status) or status)
    acked_at = str(payload.get("acked_at", "") or "").strip() or datetime.now(timezone.utc).isoformat()
    previous_ack_event_id = str(payload.get("previous_ack_event_id", "") or "").strip() or None

    session_id = str(payload.get("session_id", "") or "").strip()
    if not session_id and default_session_id:
        session_id = str(default_session_id)

    alerts = payload.get("alerts", [])
    normalized_alerts: list[dict[str, object]] = []
    if isinstance(alerts, list):
        for row in alerts:
            if isinstance(row, dict):
                normalized_alerts.append(row)

    ack_key = str(payload.get("ack_key", "") or "").strip()
    if not ack_key:
        ack_key = make_ack_key(session_id=session_id or None, window_index=window_index, timestamp=timestamp)

    ack_event_id = str(payload.get("ack_event_id", "") or payload.get("ack_id", "") or "").strip()
    if not ack_event_id:
        raw = f"{action}|{ack_key}|{acked_at}|{by}|{note}"
        ack_event_id = f"ack-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"  # noqa: S324

    return {
        "ack_event_id": ack_event_id,
        "ack_id": ack_event_id,
        "ack_key": ack_key,
        "action": action,
        "session_id": session_id or None,
        "window_index": window_index,
        "timestamp": timestamp,
        "timestamp_iso": timestamp_iso,
        "status": status,
        "alerts": normalized_alerts,
        "by": by,
        "note": note,
        "acked_at": acked_at,
        "status_at_ack": status_at_ack,
        "previous_ack_event_id": previous_ack_event_id,
    }


def make_ack_key(*, session_id: str | None, window_index: int, timestamp: int) -> str:
    return f"{session_id or '<none>'}:{int(window_index)}:{int(timestamp)}"


def ack_record_key(record: dict[str, object]) -> str | None:
    explicit = str(record.get("ack_key", "") or "").strip()
    if explicit:
        return explicit
    session_id = str(record.get("session_id", "") or "").strip() or None
    window_index = record.get("window_index")
    timestamp = record.get("timestamp")
    if window_index is None:
        return None
    try:
        index = int(window_index)
    except (TypeError, ValueError):
        return None
    return make_ack_key(session_id=session_id, window_index=index, timestamp=_to_int(timestamp, default=0))


def _to_int(value: object, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)
