"""Builds the dashboard's view of a factory run from the files in .factory/.

Read-only. The factory appends to these files while the dashboard reads them,
so every reader tolerates missing files and half-written lines.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PHASES: tuple[tuple[int, str, str], ...] = (
    (1, "Plan", "plan.md"),
    (2, "Build", "build.md"),
    (3, "Check", "report.md"),
    (4, "Review", "review.md"),
)
DOCS: tuple[str, ...] = tuple(doc for _, _, doc in PHASES)
MAX_DETAIL = 160
MAX_ACTIONS = 300

Row = dict[str, Any]


def read_jsonl(path: Path) -> list[Row]:
    """Parse a JSON-lines file, skipping blank or partial lines."""
    if not path.is_file():
        return []
    rows: list[Row] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # the last line can be mid-write
        if isinstance(row, dict):
            rows.append(row)
    return rows


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def shorten(value: Any, root: str = "") -> str:
    """One line, repo-relative paths, capped length."""
    text = " ".join(str(value).split())
    if root:
        text = text.replace(root, "")
    return text if len(text) <= MAX_DETAIL else text[:MAX_DETAIL] + "…"


def _blocks(row: Row) -> list[Row]:
    content = (row.get("message") or {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _tool_detail(tool_input: Row) -> Any:
    for key in ("command", "file_path", "pattern", "path", "url"):
        if tool_input.get(key):
            return tool_input[key]
    return ""


def _assistant_actions(row: Row, root: str) -> list[Row]:
    actions: list[Row] = []
    for block in _blocks(row):
        if block.get("type") == "tool_use":
            detail = shorten(_tool_detail(block.get("input") or {}), root)
            actions.append({"kind": "tool", "tool": block.get("name", ""), "detail": detail})
        elif block.get("type") == "text" and str(block.get("text", "")).strip():
            text = str(block["text"]).strip().replace(root, "") if root else str(block["text"]).strip()
            actions.append({"kind": "text", "detail": text})
    return actions


def _result_text(content: Any) -> str:
    if isinstance(content, list):
        return " ".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
    return str(content)


def _error_actions(row: Row, root: str) -> list[Row]:
    return [
        {"kind": "error", "detail": shorten(_result_text(b.get("content", "")), root)}
        for b in _blocks(row)
        if b.get("type") == "tool_result" and b.get("is_error") is True
    ]


def phase_actions(rows: list[Row], root: str = "") -> list[Row]:
    """The readable timeline of one phase: tool calls, failures, agent text."""
    actions: list[Row] = []
    for row in rows:
        if row.get("type") == "assistant":
            actions.extend(_assistant_actions(row, root))
        elif row.get("type") == "user":
            actions.extend(_error_actions(row, root))
    return actions[-MAX_ACTIONS:]


def phase_stats(rows: list[Row]) -> Row | None:
    """Turns, seconds and cost from the phase's final result line, if it has one."""
    result = next((r for r in reversed(rows) if r.get("type") == "result"), None)
    if result is None:
        return None
    return {
        "ok": result.get("subtype") == "success",
        "turns": int(result.get("num_turns") or 0),
        "seconds": round(float(result.get("duration_ms") or 0) / 1000),
        "cost": round(float(result.get("total_cost_usd") or 0), 4),
    }


def last_event(events: list[Row], name: str, **match: str) -> Row | None:
    for event in reversed(events):
        if event.get("event") == name and all(str(event.get(k)) == v for k, v in match.items()):
            return event
    return None


def phase_status(num: int, events: list[Row], rows: list[Row]) -> str:
    """pending -> running -> done | failed. Falls back to the log when there are no events."""
    phase = str(num)
    if last_event(events, "fail", phase=phase):
        return "failed"
    if last_event(events, "phase_end", phase=phase):
        return "done"
    if last_event(events, "phase_start", phase=phase) or rows:
        stats = phase_stats(rows)
        return "done" if stats and stats["ok"] and not events else "running"
    return "pending"


def _skipped_if_over(status: str, events: list[Row]) -> str:
    """A phase still pending when the run has finished or stopped will never run."""
    over = last_event(events, "finish") or last_event(events, "fail")
    return "skipped" if status == "pending" and over else status


def build_phase(num: int, name: str, doc: str, logs: Path, events: list[Row], root: str) -> Row:
    rows = read_jsonl(logs / f"phase{num}.jsonl")
    start = last_event(events, "phase_start", phase=str(num)) or {}
    tools = [t for t in str(start.get("tools", "")).split("|") if t]
    return {
        "num": num,
        "name": str(start.get("name") or name),  # the prompt's heading, once the phase starts
        "doc": doc,
        "status": _skipped_if_over(phase_status(num, events, rows), events),
        "tools": tools,
        "stats": phase_stats(rows),
        "actions": phase_actions(rows, root),
    }


def run_status(events: list[Row]) -> str:
    """idle | running | failed | rejected | committed | pr"""
    if not last_event(events, "run_start"):
        return "idle"
    if last_event(events, "fail"):
        return "failed"
    finish = last_event(events, "finish")
    return str(finish.get("result", "done")) if finish else "running"


def run_summary(events: list[Row]) -> Row:
    start = last_event(events, "run_start") or {}
    preflight = last_event(events, "preflight") or {}
    fail = last_event(events, "fail") or {}
    finish = last_event(events, "finish") or {}
    status = run_status(events)
    preflight_state = "ok" if preflight else ("failed" if fail else "running" if start else "pending")
    return {
        "status": status,
        "issue": start.get("issue"),
        "replay": start.get("replay") == "true",
        "title": preflight.get("title", ""),
        "branch": preflight.get("branch", ""),
        "preflight": preflight_state,
        "verdict": (last_event(events, "verdict") or {}).get("value"),
        "pr_url": finish.get("url"),
        "reason": fail.get("reason"),
        "started": start.get("ts"),
        "ended": (finish or fail).get("ts"),
    }


def build_state(factory_dir: Path, root: str = "") -> Row:
    """Everything the dashboard renders, as one JSON-serialisable dict."""
    logs = factory_dir / "logs"
    events = read_jsonl(logs / "events.jsonl")
    phases = [build_phase(n, name, doc, logs, events, root) for n, name, doc in PHASES]
    return {
        "run": run_summary(events),
        "phases": phases,
        "gates": [e for e in events if e.get("event") in ("scope", "gate")],  # scope checks and participant gates
        "docs": {doc: read_text(factory_dir / doc) for doc in DOCS},
        "cost": round(sum(p["stats"]["cost"] for p in phases if p["stats"]), 4),
    }
