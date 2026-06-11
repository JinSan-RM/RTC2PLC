from __future__ import annotations

from collections import Counter


REQUIRED_ENVELOPE_FIELDS = (
    "stream_version",
    "kind",
    "message_id",
    "sequence",
)


def validate_stream_messages(messages: list[dict[str, object]]) -> dict[str, object]:
    kind_counts: Counter[str] = Counter()
    duplicates: list[str] = []
    missing_fields: list[dict[str, object]] = []
    sequence_violations: list[dict[str, object]] = []
    violations: list[dict[str, object]] = []
    seen_message_ids: set[str] = set()
    last_sequence: int | None = None

    for index, message in enumerate(messages):
        kind = str(message.get("kind", "")).strip() or "<unknown>"
        kind_counts[kind] += 1

        missing = [field for field in REQUIRED_ENVELOPE_FIELDS if field not in message]
        if missing:
            missing_fields.append({"index": index, "missing_fields": missing})
            continue

        message_id = str(message.get("message_id", "")).strip()
        if not message_id:
            missing_fields.append({"index": index, "missing_fields": ["message_id"]})
        elif message_id in seen_message_ids:
            duplicates.append(message_id)
        else:
            seen_message_ids.add(message_id)

        try:
            sequence = int(message.get("sequence"))
        except (TypeError, ValueError):
            sequence_violations.append({"index": index, "reason": "sequence_not_integer"})
            continue
        if sequence <= 0:
            sequence_violations.append({"index": index, "reason": "sequence_must_be_positive", "sequence": sequence})
        if last_sequence is not None and sequence <= last_sequence:
            sequence_violations.append(
                {
                    "index": index,
                    "reason": "sequence_not_strictly_increasing",
                    "sequence": sequence,
                    "previous_sequence": last_sequence,
                }
            )
        last_sequence = sequence

    if duplicates:
        violations.append(
            {
                "code": "DUPLICATE_MESSAGE_ID",
                "count": len(duplicates),
                "message_ids": sorted(set(duplicates)),
            }
        )
    if missing_fields:
        violations.append(
            {
                "code": "MISSING_REQUIRED_FIELDS",
                "count": len(missing_fields),
                "entries": missing_fields,
            }
        )
    if sequence_violations:
        violations.append(
            {
                "code": "SEQUENCE_VIOLATION",
                "count": len(sequence_violations),
                "entries": sequence_violations,
            }
        )

    summary_count = int(kind_counts.get("runtime_summary", 0))
    if summary_count != 1:
        violations.append(
            {
                "code": "SUMMARY_COUNT_INVALID",
                "count": summary_count,
                "expected": 1,
            }
        )

    return {
        "message_count": len(messages),
        "kind_counts": dict(kind_counts),
        "duplicate_message_ids": sorted(set(duplicates)),
        "missing_required_fields": missing_fields,
        "sequence_violations": sequence_violations,
        "violations": violations,
        "violation_count": len(violations),
    }
