from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from common.paths import ensure_directory
from runtime.replay_runtime import RuntimeWindowResult


@dataclass(slots=True)
class DashboardThresholds:
    max_unknown_ratio: float = 0.15
    max_dropped_small_components: int = 64
    min_objects_per_window: int = 1

    def normalized(self) -> DashboardThresholds:
        return DashboardThresholds(
            max_unknown_ratio=min(max(float(self.max_unknown_ratio), 0.0), 1.0),
            max_dropped_small_components=max(0, int(self.max_dropped_small_components)),
            min_objects_per_window=max(0, int(self.min_objects_per_window)),
        )


def build_runtime_dashboard_payload(
    *,
    results: list[RuntimeWindowResult],
    runtime_summary: dict[str, object],
    thresholds: DashboardThresholds,
) -> dict[str, object]:
    normalized = thresholds.normalized()
    windows: list[dict[str, object]] = []
    status_counts = {"ok": 0, "warning": 0, "critical": 0}
    max_unknown_ratio = 0.0
    max_dropped_small_components = 0

    for item in results:
        event = item.event if isinstance(item.event, dict) else {}
        objects = event.get("objects", [])
        object_rows = objects if isinstance(objects, list) else []
        object_count = len(object_rows)
        unknown_ratio = _as_float(item.pixel_summary.get("unknown_ratio"), default=0.0)
        alarm_unknown_ratio = _as_float(
            item.pixel_summary.get("actionable_unknown_ratio"),
            default=unknown_ratio,
        )
        dropped_small_components = _as_int(
            item.object_summary.get("dropped_small_components"),
            default=0,
        )

        max_unknown_ratio = max(max_unknown_ratio, unknown_ratio)
        max_dropped_small_components = max(max_dropped_small_components, dropped_small_components)

        alerts = _build_window_alerts(
            object_count=object_count,
            unknown_ratio=alarm_unknown_ratio,
            dropped_small_components=dropped_small_components,
            thresholds=normalized,
        )
        status = _resolve_status(alerts)
        status_counts[status] += 1
        objects_per_class = _extract_objects_per_class(item.object_summary)
        windows.append(
            {
                "window_index": int(item.window_index),
                "frame_range": [int(item.frame_start), int(item.frame_end)],
                "timestamp": _as_int(event.get("timestamp"), default=0),
                "timestamp_iso": str(event.get("timestamp_iso", "")),
                "object_count": object_count,
                "objects_per_class": objects_per_class,
                "dominant_class": _resolve_dominant_class(objects_per_class),
                "dropped_small_components": dropped_small_components,
                "unknown_ratio": unknown_ratio,
                "alarm_unknown_ratio": alarm_unknown_ratio,
                "known_pixels": _as_int(item.pixel_summary.get("known_pixels"), default=0),
                "unknown_pixels": _as_int(item.pixel_summary.get("unknown_pixels"), default=0),
                "low_confidence_pixels": _as_int(item.pixel_summary.get("low_confidence_pixels"), default=0),
                "ignored_pixels": _as_int(item.pixel_summary.get("ignored_pixels"), default=0),
                "invalid_x_pixels": _as_int(item.pixel_summary.get("invalid_x_pixels"), default=0),
                "actionable_unknown_pixels": _as_int(
                    item.pixel_summary.get("actionable_unknown_pixels"),
                    default=_as_int(item.pixel_summary.get("unknown_pixels"), default=0),
                ),
                "alerts": alerts,
                "status": status,
                "objects": _normalize_objects_for_ui(object_rows),
            }
        )

    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_summary": runtime_summary,
        "thresholds": {
            "max_unknown_ratio": float(normalized.max_unknown_ratio),
            "max_dropped_small_components": int(normalized.max_dropped_small_components),
            "min_objects_per_window": int(normalized.min_objects_per_window),
        },
        "window_count": len(windows),
        "status_counts": status_counts,
        "max_unknown_ratio": float(max_unknown_ratio),
        "max_alarm_unknown_ratio": float(
            max((_as_float(row.get("alarm_unknown_ratio"), default=0.0) for row in windows), default=0.0)
        ),
        "max_dropped_small_components": int(max_dropped_small_components),
        "windows": windows,
    }


def write_runtime_dashboard_html(path: Path, payload: dict[str, object]) -> Path:
    ensure_directory(path.parent)
    payload_json = json.dumps(payload, ensure_ascii=False)
    html = _build_dashboard_html(payload_json)
    path.write_text(html, encoding="utf-8")
    return path


def _build_window_alerts(
    *,
    object_count: int,
    unknown_ratio: float,
    dropped_small_components: int,
    thresholds: DashboardThresholds,
) -> list[dict[str, object]]:
    alerts: list[dict[str, object]] = []
    if thresholds.min_objects_per_window > 0 and object_count < thresholds.min_objects_per_window:
        alerts.append(
            {
                "severity": "critical",
                "code": "LOW_OBJECT_COUNT",
                "message": f"object_count={object_count} < {thresholds.min_objects_per_window}",
            }
        )
    if unknown_ratio > thresholds.max_unknown_ratio:
        alerts.append(
            {
                "severity": "warning",
                "code": "HIGH_UNKNOWN_RATIO",
                "message": f"alarm_unknown_ratio={unknown_ratio:.4f} > {thresholds.max_unknown_ratio:.4f}",
            }
        )
    if dropped_small_components > thresholds.max_dropped_small_components:
        alerts.append(
            {
                "severity": "warning",
                "code": "HIGH_DROPPED_COMPONENTS",
                "message": (
                    f"dropped_small_components={dropped_small_components} > "
                    f"{thresholds.max_dropped_small_components}"
                ),
            }
        )
    return alerts


def _resolve_status(alerts: list[dict[str, object]]) -> str:
    if any(str(item.get("severity")) == "critical" for item in alerts):
        return "critical"
    if alerts:
        return "warning"
    return "ok"


def _extract_objects_per_class(payload: dict[str, object]) -> dict[str, int]:
    maybe = payload.get("objects_per_class")
    if not isinstance(maybe, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, value in maybe.items():
        normalized[str(key)] = max(0, int(value))
    return normalized


def _resolve_dominant_class(class_counts: dict[str, int]) -> str:
    if not class_counts:
        return "none"
    return max(class_counts.items(), key=lambda item: item[1])[0]


def _normalize_objects_for_ui(rows: list[Any]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized.append(
            {
                "class": str(row.get("class", "unknown")),
                "confidence": _as_float(row.get("confidence"), default=0.0),
                "bbox": _normalize_bbox(row.get("bbox")),
                "frame_range": _normalize_frame_range(row.get("frame_range")),
            }
        )
    normalized.sort(key=lambda item: float(item["confidence"]), reverse=True)
    return normalized


def _normalize_bbox(value: object) -> list[int]:
    if not isinstance(value, list) or len(value) != 4:
        return [0, 0, 0, 0]
    return [int(v) for v in value]


def _normalize_frame_range(value: object) -> list[int]:
    if not isinstance(value, list) or len(value) != 2:
        return [0, 0]
    return [int(value[0]), int(value[1])]


def _as_int(value: object, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _as_float(value: object, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _build_dashboard_html(payload_json: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Spectral Runtime Dashboard</title>
  <style>
    :root {{
      --bg-0: #0b1320;
      --bg-1: #13253f;
      --panel: rgba(9, 18, 31, 0.78);
      --panel-border: rgba(127, 179, 213, 0.28);
      --text: #e7eef7;
      --muted: #9db0c4;
      --ok: #2fc18f;
      --warn: #f2a93b;
      --critical: #e64957;
      --accent: #5bc0eb;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      font-family: "Bahnschrift", "Segoe UI Variable", "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(160% 120% at 20% 0%, #25406a 0%, transparent 55%),
        radial-gradient(180% 130% at 100% 0%, #20463f 0%, transparent 50%),
        linear-gradient(165deg, var(--bg-0) 0%, var(--bg-1) 100%);
      min-height: 100vh;
      padding: 24px;
    }}
    .layout {{
      max-width: 1440px;
      margin: 0 auto;
      display: grid;
      gap: 16px;
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: end;
      gap: 16px;
    }}
    h1 {{
      margin: 0;
      font-size: 26px;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      font-weight: 700;
    }}
    .sub {{
      margin-top: 6px;
      color: var(--muted);
      font-size: 13px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 14px;
      padding: 14px;
      backdrop-filter: blur(2px);
    }}
    .label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .value {{
      margin-top: 8px;
      font-size: 28px;
      font-weight: 700;
      line-height: 1.1;
    }}
    .status-row {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 8px;
      font-size: 12px;
    }}
    .status-chip {{
      padding: 3px 8px;
      border-radius: 999px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .ok {{
      color: #052015;
      background: var(--ok);
    }}
    .warning {{
      color: #2f1b00;
      background: var(--warn);
    }}
    .critical {{
      color: #2a0006;
      background: var(--critical);
    }}
    .table-wrap {{
      overflow: auto;
      border-radius: 14px;
      border: 1px solid var(--panel-border);
      background: var(--panel);
    }}
    .toolbar {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 14px;
      padding: 12px;
    }}
    .toolbar .control {{
      display: grid;
      gap: 6px;
    }}
    .toolbar label {{
      font-size: 11px;
      letter-spacing: 0.07em;
      color: var(--muted);
      text-transform: uppercase;
    }}
    .toolbar select,
    .toolbar input,
    .toolbar button {{
      width: 100%;
      border: 1px solid rgba(151, 176, 201, 0.28);
      border-radius: 9px;
      padding: 8px 10px;
      font-size: 13px;
      color: var(--text);
      background: rgba(8, 15, 26, 0.82);
      outline: none;
    }}
    .toolbar button {{
      cursor: pointer;
      background: linear-gradient(160deg, rgba(50, 127, 219, 0.82), rgba(33, 101, 164, 0.82));
      border: none;
      font-weight: 700;
    }}
    .toolbar button.secondary {{
      background: rgba(48, 68, 91, 0.84);
    }}
    .toolbar .inline {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 4px;
      font-size: 12px;
      color: var(--muted);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 1080px;
    }}
    thead th {{
      text-align: left;
      font-size: 12px;
      letter-spacing: 0.07em;
      color: var(--muted);
      text-transform: uppercase;
      padding: 12px 14px;
      background: rgba(8, 18, 33, 0.88);
      position: sticky;
      top: 0;
    }}
    tbody td {{
      padding: 10px 14px;
      border-top: 1px solid rgba(152, 178, 201, 0.12);
      font-size: 13px;
    }}
    tbody tr {{
      cursor: pointer;
      transition: background-color 0.16s ease;
    }}
    tbody tr:hover {{
      background: rgba(91, 192, 235, 0.08);
    }}
    tbody tr.selected {{
      background: rgba(91, 192, 235, 0.14);
    }}
    .details {{
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 14px;
      padding: 14px;
    }}
    .details h2 {{
      margin: 0 0 10px 0;
      font-size: 16px;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }}
    .details-layout {{
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 12px;
    }}
    .ack-log {{
      border: 1px solid rgba(151, 176, 201, 0.24);
      border-radius: 10px;
      padding: 10px;
      max-height: 220px;
      overflow: auto;
      background: rgba(10, 21, 35, 0.64);
      font-size: 12px;
      line-height: 1.45;
    }}
    .ack-item {{
      padding: 8px;
      border-bottom: 1px solid rgba(151, 176, 201, 0.16);
    }}
    .ack-item:last-child {{
      border-bottom: none;
    }}
    .ack-tag {{
      display: inline-block;
      padding: 2px 6px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.04em;
      background: rgba(47, 193, 143, 0.18);
      color: #92f3cd;
    }}
    .ack-col {{
      font-size: 12px;
      color: var(--muted);
    }}
    .mono {{
      font-family: "Consolas", "Cascadia Mono", monospace;
      font-size: 12px;
      color: #c8d5e5;
      white-space: pre-wrap;
      line-height: 1.45;
    }}
    @media (max-width: 1100px) {{
      .grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .toolbar {{
        grid-template-columns: 1fr 1fr;
      }}
      .details-layout {{
        grid-template-columns: 1fr;
      }}
    }}
    @media (max-width: 700px) {{
      body {{
        padding: 12px;
      }}
      .grid {{
        grid-template-columns: 1fr;
      }}
      .toolbar {{
        grid-template-columns: 1fr;
      }}
      h1 {{
        font-size: 20px;
      }}
    }}
  </style>
</head>
<body>
  <div class="layout" id="runtime-dashboard-root">
    <section class="header">
      <div>
        <h1>Runtime Monitor</h1>
        <div class="sub" id="generated-at"></div>
      </div>
      <div class="sub" id="thresholds"></div>
    </section>
    <section class="grid">
      <article class="card">
        <div class="label">Windows</div>
        <div class="value" id="kpi-window-count">0</div>
      </article>
      <article class="card">
        <div class="label">Total Objects</div>
        <div class="value" id="kpi-total-objects">0</div>
      </article>
      <article class="card">
        <div class="label">Dropped Components</div>
        <div class="value" id="kpi-dropped">0</div>
      </article>
      <article class="card">
        <div class="label">Alarm Windows</div>
        <div class="value" id="kpi-alarms">0</div>
      </article>
      <article class="card">
        <div class="label">Peak Unknown Ratio</div>
        <div class="value" id="kpi-unknown">0</div>
      </article>
      <article class="card">
        <div class="label">Acknowledged</div>
        <div class="value" id="kpi-ack-count">0</div>
      </article>
    </section>
    <section class="toolbar">
      <div class="control">
        <label for="status-filter">Status Filter</label>
        <select id="status-filter">
          <option value="all">all</option>
          <option value="alarm">alarm (warning+critical)</option>
          <option value="critical">critical</option>
          <option value="warning">warning</option>
          <option value="ok">ok</option>
          <option value="acked">acked</option>
          <option value="unacked">unacked</option>
        </select>
      </div>
      <div class="control">
        <label for="sort-mode">Sort Mode</label>
        <select id="sort-mode">
          <option value="status">status</option>
          <option value="timestamp_desc">timestamp desc</option>
          <option value="timestamp_asc">timestamp asc</option>
          <option value="objects_desc">object_count desc</option>
          <option value="unknown_desc">unknown_ratio desc</option>
          <option value="dropped_desc">dropped desc</option>
        </select>
        <div class="inline">
          <input id="critical-first" type="checkbox" checked />
          <label for="critical-first">critical first</label>
        </div>
      </div>
      <div class="control">
        <label for="ack-user">Ack User</label>
        <input id="ack-user" placeholder="operator id" />
      </div>
      <div class="control">
        <label for="ack-note">Ack Note</label>
        <input id="ack-note" placeholder="note (optional)" />
      </div>
      <div class="control">
        <label>Actions</label>
        <button id="ack-selected-btn">Acknowledge Selected</button>
        <button id="cancel-ack-btn" class="secondary">Cancel Selected Ack</button>
        <button id="export-ack-jsonl-btn" class="secondary">Export Ack JSONL</button>
        <button id="clear-ack-btn" class="secondary">Clear Ack Log</button>
      </div>
    </section>
    <section class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Window</th>
            <th>Timestamp</th>
            <th>Frames</th>
            <th>Status</th>
            <th>Objects</th>
            <th>Dropped</th>
            <th>Unknown Ratio</th>
            <th>Dominant Class</th>
            <th>Alerts</th>
            <th>Ack</th>
          </tr>
        </thead>
        <tbody id="window-table-body"></tbody>
      </table>
    </section>
    <section class="details">
      <h2>Window Detail</h2>
      <div class="details-layout">
        <div class="mono" id="window-detail"></div>
        <div class="ack-log" id="ack-log"></div>
      </div>
    </section>
  </div>

  <script id="dashboard-data" type="application/json">{payload_json}</script>
  <script>
    const data = JSON.parse(document.getElementById("dashboard-data").textContent);
    const windows = Array.isArray(data.windows) ? data.windows : [];

    const runtimeSummary = data.runtime_summary || {{}};
    const statusCounts = data.status_counts || {{}};
    const thresholds = data.thresholds || {{}};
    const storageKey = "spectral-runtime-dashboard-acks-v1";

    const num = (value, digits = 0) => {{
      const n = Number(value);
      if (!Number.isFinite(n)) return "0";
      return n.toFixed(digits);
    }};
    const escapeHtml = (value) =>
      String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");

    document.getElementById("generated-at").textContent =
      `generated_at=${{data.created_at_utc || "n/a"}}`;
    document.getElementById("thresholds").textContent =
      `thresholds: unknown<=${{num(thresholds.max_unknown_ratio, 2)}}, ` +
      `dropped<=${{num(thresholds.max_dropped_small_components, 0)}}, ` +
      `min_objects=${{num(thresholds.min_objects_per_window, 0)}}`;
    document.getElementById("kpi-window-count").textContent =
      String(data.window_count ?? runtimeSummary.window_count ?? 0);
    document.getElementById("kpi-total-objects").textContent =
      String(runtimeSummary.total_objects ?? 0);
    document.getElementById("kpi-dropped").textContent =
      String(runtimeSummary.total_dropped_small_components ?? 0);
    document.getElementById("kpi-alarms").textContent =
      String((statusCounts.warning || 0) + (statusCounts.critical || 0));
    document.getElementById("kpi-unknown").textContent =
      num(data.max_unknown_ratio || 0, 3);

    const tbody = document.getElementById("window-table-body");
    const detail = document.getElementById("window-detail");
    const ackLog = document.getElementById("ack-log");
    const statusFilter = document.getElementById("status-filter");
    const sortMode = document.getElementById("sort-mode");
    const criticalFirst = document.getElementById("critical-first");
    const ackUserInput = document.getElementById("ack-user");
    const ackNoteInput = document.getElementById("ack-note");
    const ackSelectedBtn = document.getElementById("ack-selected-btn");
    const cancelAckBtn = document.getElementById("cancel-ack-btn");
    const clearAckBtn = document.getElementById("clear-ack-btn");
    const exportAckJsonlBtn = document.getElementById("export-ack-jsonl-btn");

    const fmtFrameRange = (range) => {{
      if (!Array.isArray(range) || range.length !== 2) return "n/a";
      return `${{range[0]}}-${{range[1]}}`;
    }};
    const fmtAlerts = (alerts) => {{
      if (!Array.isArray(alerts) || alerts.length === 0) return "none";
      return alerts.map((x) => x.code).join(", ");
    }};
    const statusClass = (status) => {{
      if (status === "critical") return "critical";
      if (status === "warning") return "warning";
      return "ok";
    }};
    const statusRank = (status) => {{
      if (status === "critical") return 3;
      if (status === "warning") return 2;
      return 1;
    }};
    const windowKey = (windowData) => `${{windowData.window_index}}:${{windowData.timestamp || 0}}`;
    const loadAckStore = () => {{
      try {{
        const raw = localStorage.getItem(storageKey);
        if (!raw) return {{}};
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === "object" ? parsed : {{}};
      }} catch (error) {{
        return {{}};
      }}
    }};
    const saveAckStore = (store) => {{
      localStorage.setItem(storageKey, JSON.stringify(store));
    }};
    const ackStore = loadAckStore();
    const getAck = (windowData) => ackStore[windowKey(windowData)] || null;
    const isAcked = (windowData) => !!getAck(windowData);
    const ackExport = data.ack_export || {{}};
    const ackApi = data.ack_api || {{}};
    const ackApiEnabled = Boolean(ackApi.enabled) && typeof fetch === "function";
    const ackListUrl = typeof ackApi.list_url === "string" ? ackApi.list_url : "";
    const ackPostUrl = typeof ackApi.post_url === "string" ? ackApi.post_url : "";
    const ackHistoryUrl = typeof ackApi.history_url === "string" ? ackApi.history_url : "";
    const ackApiToken = typeof ackApi.token === "string" ? ackApi.token : "";

    let selectedRow = null;
    let selectedWindow = null;

    const updateAckKpi = () => {{
      const ackCount = windows.filter((item) => isAcked(item)).length;
      document.getElementById("kpi-ack-count").textContent = String(ackCount);
    }};

    const setDetail = (windowData) => {{
      const ack = getAck(windowData);
      const payload = {{
        window_index: windowData.window_index,
        timestamp_iso: windowData.timestamp_iso,
        frame_range: windowData.frame_range,
        object_count: windowData.object_count,
        dominant_class: windowData.dominant_class,
        dropped_small_components: windowData.dropped_small_components,
        unknown_ratio: windowData.unknown_ratio,
        alerts: windowData.alerts,
        objects: windowData.objects.slice(0, 12),
        ack: ack,
      }};
      detail.textContent = JSON.stringify(payload, null, 2);
      selectedWindow = windowData;
    }};

    const passesFilter = (windowData) => {{
      const mode = statusFilter.value;
      if (mode === "all") return true;
      if (mode === "alarm") return windowData.status === "critical" || windowData.status === "warning";
      if (mode === "acked") return isAcked(windowData);
      if (mode === "unacked") return !isAcked(windowData);
      return windowData.status === mode;
    }};

    const compareWindows = (left, right) => {{
      const mode = sortMode.value;
      if (mode === "timestamp_desc") return (right.timestamp || 0) - (left.timestamp || 0);
      if (mode === "timestamp_asc") return (left.timestamp || 0) - (right.timestamp || 0);
      if (mode === "objects_desc") return (right.object_count || 0) - (left.object_count || 0);
      if (mode === "unknown_desc") return (right.unknown_ratio || 0) - (left.unknown_ratio || 0);
      if (mode === "dropped_desc") return (right.dropped_small_components || 0) - (left.dropped_small_components || 0);
      return statusRank(right.status) - statusRank(left.status);
    }};

    const renderAckLog = () => {{
      const rows = windows
        .map((item) => {{
          const ack = getAck(item);
          if (!ack) return null;
          return {{
            window_index: item.window_index,
            timestamp_iso: item.timestamp_iso,
            status: item.status,
            by: ack.by || "",
            at: ack.at || "",
            note: ack.note || "",
          }};
        }})
        .filter((item) => item !== null)
        .sort((a, b) => (String(b.at) > String(a.at) ? 1 : -1));
      if (rows.length === 0) {{
        ackLog.innerHTML = "<div>No acknowledgements yet.</div>";
        return;
      }}
      ackLog.innerHTML = rows
        .map(
          (row) => `
            <div class="ack-item">
              <div><span class="ack-tag">${{escapeHtml(row.status)}}</span> window=${{escapeHtml(row.window_index)}} @ ${{escapeHtml(row.timestamp_iso || "n/a")}}</div>
              <div class="ack-col">by=${{escapeHtml(row.by)}} at=${{escapeHtml(row.at)}}</div>
              <div class="ack-col">${{escapeHtml(row.note || "")}}</div>
            </div>
          `
        )
        .join("");
    }};

    const renderTable = () => {{
      tbody.innerHTML = "";
      if (selectedRow) {{
        selectedRow.classList.remove("selected");
        selectedRow = null;
      }}
      const filtered = windows.filter((item) => passesFilter(item));
      filtered.sort((a, b) => {{
        const base = compareWindows(a, b);
        if (criticalFirst.checked) {{
          const criticalBias = statusRank(b.status) - statusRank(a.status);
          if (criticalBias !== 0) return criticalBias;
        }}
        if (base !== 0) return base;
        return (a.window_index || 0) - (b.window_index || 0);
      }});

      filtered.forEach((windowData) => {{
        const tr = document.createElement("tr");
        const ack = getAck(windowData);
        const ackLabel = ack ? `<span class="ack-tag">${{escapeHtml(ack.by || "acked")}}</span>` : "-";
        tr.innerHTML = `
          <td>${{escapeHtml(windowData.window_index)}}</td>
          <td>${{escapeHtml(windowData.timestamp_iso || windowData.timestamp || "n/a")}}</td>
          <td>${{escapeHtml(fmtFrameRange(windowData.frame_range))}}</td>
          <td><span class="status-chip ${{statusClass(windowData.status)}}">${{escapeHtml(windowData.status)}}</span></td>
          <td>${{escapeHtml(windowData.object_count)}}</td>
          <td>${{escapeHtml(windowData.dropped_small_components)}}</td>
          <td>${{escapeHtml(num(windowData.unknown_ratio, 4))}}</td>
          <td>${{escapeHtml(windowData.dominant_class || "none")}}</td>
          <td>${{escapeHtml(fmtAlerts(windowData.alerts))}}</td>
          <td>${{ackLabel}}</td>
        `;
        tr.addEventListener("click", () => {{
          if (selectedRow) selectedRow.classList.remove("selected");
          selectedRow = tr;
          selectedRow.classList.add("selected");
          setDetail(windowData);
        }});
        tbody.appendChild(tr);
      }});

      if (tbody.firstElementChild && filtered.length > 0) {{
        tbody.firstElementChild.classList.add("selected");
        selectedRow = tbody.firstElementChild;
        setDetail(filtered[0]);
      }} else {{
        detail.textContent = "No windows matched the filter.";
        selectedWindow = null;
      }}
      renderAckLog();
      updateAckKpi();
    }};

    const ackFromRecord = (record) => {{
      if (!record || typeof record !== "object") return null;
      return {{
        by: String(record.by || ""),
        note: String(record.note || ""),
        at: String(record.acked_at || record.at || ""),
        status_at_ack: String(record.status_at_ack || record.status || ""),
      }};
    }};
    const buildAckPayload = (windowData, ackState, action = "ack") => {{
      return {{
        action: action,
        ack_key: windowKey(windowData),
        session_id: ackExport.session_id || ackApi.session_id || null,
        window_index: windowData.window_index,
        timestamp: windowData.timestamp,
        timestamp_iso: windowData.timestamp_iso,
        status: windowData.status,
        alerts: windowData.alerts || [],
        by: ackState.by || "",
        note: ackState.note || "",
        acked_at: ackState.at || "",
        status_at_ack: ackState.status_at_ack || windowData.status,
      }};
    }};
    const hydrateRemoteAcks = async () => {{
      if (!ackApiEnabled || !ackListUrl) return;
      try {{
        const headers = {{
          "Accept": "application/json",
        }};
        if (ackApiToken) {{
          headers["X-Ack-Token"] = ackApiToken;
        }}
        const response = await fetch(ackListUrl, {{
          method: "GET",
          headers: headers,
        }});
        if (!response.ok) return;
        const payload = await response.json();
        const records = Array.isArray(payload.records) ? payload.records : [];
        records.forEach((record) => {{
          if (!record || typeof record !== "object") return;
          const key = `${{record.window_index}}:${{record.timestamp || 0}}`;
          const ack = ackFromRecord(record);
          if (ack) ackStore[key] = ack;
        }});
        saveAckStore(ackStore);
      }} catch (error) {{
        // Fallback to localStorage-only mode when ack API is unavailable.
      }}
    }};
    const persistAckRemote = async (windowData, ackState, action = "ack") => {{
      if (!ackApiEnabled || !ackPostUrl) return {{ ok: false, reason: "disabled" }};
      try {{
        const headers = {{
          "Content-Type": "application/json",
          "Accept": "application/json",
        }};
        if (ackApiToken) {{
          headers["X-Ack-Token"] = ackApiToken;
        }}
        const response = await fetch(ackPostUrl, {{
          method: "POST",
          headers: headers,
          body: JSON.stringify(buildAckPayload(windowData, ackState, action)),
        }});
        if (!response.ok) {{
          return {{ ok: false, reason: `http_${{response.status}}` }};
        }}
        const payload = await response.json();
        const record = payload && payload.record ? payload.record : null;
        const ack = ackFromRecord(record);
        if (ack) {{
          ackStore[windowKey(windowData)] = ack;
          saveAckStore(ackStore);
        }}
        return {{ ok: true, reason: "" }};
      }} catch (error) {{
        return {{ ok: false, reason: String(error) }};
      }}
    }};

    ackSelectedBtn.addEventListener("click", async () => {{
      if (!selectedWindow) {{
        detail.textContent = "Select a window first.";
        return;
      }}
      const user = String(ackUserInput.value || "").trim();
      if (!user) {{
        detail.textContent = "Ack user is required.";
        return;
      }}
      const note = String(ackNoteInput.value || "").trim();
      const ackState = {{
        by: user,
        note: note,
        at: new Date().toISOString(),
        status_at_ack: selectedWindow.status,
      }};
      const action = isAcked(selectedWindow) ? "update" : "ack";
      ackStore[windowKey(selectedWindow)] = ackState;
      saveAckStore(ackStore);
      const remoteResult = await persistAckRemote(selectedWindow, ackState, action);
      renderTable();
      setDetail(selectedWindow);
      if (ackApiEnabled && !remoteResult.ok) {{
        detail.textContent += `\\n\\nremote_ack=failed reason=${{remoteResult.reason}}`;
      }}
    }});

    cancelAckBtn.addEventListener("click", async () => {{
      if (!selectedWindow) {{
        detail.textContent = "Select a window first.";
        return;
      }}
      if (!isAcked(selectedWindow)) {{
        detail.textContent = "Selected window is not acknowledged.";
        return;
      }}
      const user = String(ackUserInput.value || "").trim();
      if (!user) {{
        detail.textContent = "Ack user is required for cancel action.";
        return;
      }}
      const note = String(ackNoteInput.value || "").trim();
      const ackState = {{
        by: user,
        note: note,
        at: new Date().toISOString(),
        status_at_ack: selectedWindow.status,
      }};
      delete ackStore[windowKey(selectedWindow)];
      saveAckStore(ackStore);
      const remoteResult = await persistAckRemote(selectedWindow, ackState, "cancel");
      renderTable();
      if (!selectedWindow) {{
        detail.textContent = "No windows matched the filter.";
      }} else {{
        setDetail(selectedWindow);
      }}
      if (ackApiEnabled && !remoteResult.ok) {{
        detail.textContent += `\\n\\nremote_cancel=failed reason=${{remoteResult.reason}}`;
      }}
    }});

    exportAckJsonlBtn.addEventListener("click", () => {{
      const ackedRows = windows
        .map((item) => {{
          const ack = getAck(item);
          if (!ack) return null;
          return {{
            session_id: ackExport.session_id || ackApi.session_id || null,
            window_index: item.window_index,
            timestamp: item.timestamp,
            timestamp_iso: item.timestamp_iso,
            status: item.status,
            alerts: item.alerts || [],
            by: ack.by || "",
            note: ack.note || "",
            acked_at: ack.at || "",
            status_at_ack: ack.status_at_ack || item.status,
          }};
        }})
        .filter((item) => item !== null);
      if (ackedRows.length === 0) {{
        detail.textContent = "No ACK records to export.";
        return;
      }}
      const lines = ackedRows.map((row) => JSON.stringify(row)).join("\\n") + "\\n";
      const blob = new Blob([lines], {{ type: "application/x-ndjson;charset=utf-8" }});
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      const fallbackName = "ack-log.jsonl";
      anchor.href = url;
      anchor.download = ackExport.default_filename || fallbackName;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    }});

    clearAckBtn.addEventListener("click", () => {{
      const ok = window.confirm("Clear all local acknowledgements?");
      if (!ok) return;
      Object.keys(ackStore).forEach((key) => delete ackStore[key]);
      saveAckStore(ackStore);
      renderTable();
    }});

    statusFilter.addEventListener("change", renderTable);
    sortMode.addEventListener("change", renderTable);
    criticalFirst.addEventListener("change", renderTable);

    const bootstrap = async () => {{
      await hydrateRemoteAcks();
      renderTable();
    }};
    bootstrap();
  </script>
</body>
</html>
"""
