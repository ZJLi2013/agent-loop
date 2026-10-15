from __future__ import annotations

from typing import Any

LEVELS = ("must", "suggest")
MAX_PER_LEVEL = 3


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def normalize_findings(items: Any) -> tuple[list[dict[str, Any]], int, str | None]:
    if not isinstance(items, list):
        return [], 0, "findings must be a list"
    kept: dict[str, list[dict[str, Any]]] = {level: [] for level in LEVELS}
    dropped = 0
    for item in items:
        if not isinstance(item, dict) or item.get("level") not in LEVELS or not _text(item.get("claim")):
            return [], 0, "each finding needs level (must | suggest) and a claim"
        entry = {key: _text(item.get(key)) for key in ("claim", "consequence", "evidence", "change")}
        level = item["level"]
        # A must without a stated consequence and evidence is a rigor note.
        if level == "must" and not (entry["consequence"] and entry["evidence"]):
            level = "suggest"
        entry["level"] = level
        entry["human"] = level == "must" and item.get("human") is True
        if len(kept[level]) < MAX_PER_LEVEL:
            kept[level].append(entry)
        else:
            dropped += 1
    return kept["must"] + kept["suggest"], dropped, None


def describe(findings: list[dict[str, Any]]) -> str:
    return " ".join(
        f"{'Must' if item['level'] == 'must' else 'Suggest'}: {item['claim']}"
        + (f" ({item['consequence']})" if item["level"] == "must" else "")
        for item in findings
    )
