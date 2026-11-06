"""Replay a recorded factory run into .factory/ so the dashboard animates it, or record one.

  python -m dashboard.replay                  replay dashboard/sample-run (no tokens spent)
  python -m dashboard.replay --speed 2        twice as fast
  python -m dashboard.replay --record         save the last real run in .factory/ as the sample

A replay writes the same files a real run writes, so it doubles as a stage fallback.
Run ./reset.sh (or pass --force) first if .factory/ holds a run you want to keep.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from dashboard.state import DOCS, PHASES, Row, read_jsonl

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = Path(__file__).resolve().parent / "sample-run"
FACTORY = ROOT / ".factory"
DOC_FOR_PHASE = {str(num): doc for num, _, doc in PHASES}
PAUSE = {"tool_use": 0.9, "text": 1.4, "error": 0.7, "result": 0.4, "event": 0.8}
MAX_RESULT_CHARS = 400
VENV_PATH = re.compile(r"(?:(?:\.\./)*\.\./?)?~/[^\s\"]*?/venv/")


# ── record ──────────────────────────────────────────────────
def _trim_blocks(blocks: list[Any]) -> list[Row]:
    kept: list[Row] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "tool_use":
            kept.append({"type": "tool_use", "name": b.get("name"), "input": b.get("input") or {}})
        elif b.get("type") == "text":
            kept.append({"type": "text", "text": b.get("text", "")})
        elif b.get("type") == "tool_result" and b.get("is_error") is True:
            text = str(b.get("content", ""))[:MAX_RESULT_CHARS]
            kept.append({"type": "tool_result", "is_error": True, "content": text})
    return kept


def trim_row(row: Row) -> Row | None:
    """Keep only what the dashboard shows; drop thinking, usage, ids and tool output."""
    kind = row.get("type")
    if kind == "result":
        keys = ("type", "subtype", "num_turns", "duration_ms", "total_cost_usd")
        return {k: row.get(k) for k in keys}
    if kind not in ("assistant", "user"):
        return None
    content = (row.get("message") or {}).get("content")
    blocks = _trim_blocks(content) if isinstance(content, list) else []
    return {"type": kind, "message": {"content": blocks}} if blocks else None


def sanitize(line: str, run_root: Path) -> str:
    """Make paths repo-relative and drop the recorder's home directory."""
    line = line.replace(f"{run_root}/", "").replace(str(run_root), ".").replace(str(Path.home()), "~")
    return VENV_PATH.sub("venv/", line)  # pytest's "../../../..~/x/demo-factory/venv/" -> "venv/"


def record(source: Path, sample: Path) -> None:
    events = source / "logs" / "events.jsonl"
    if not events.is_file():
        sys.exit(f"No run to record: {events} is missing.")
    shutil.rmtree(sample, ignore_errors=True)
    (sample / "logs").mkdir(parents=True)
    shutil.copy(events, sample / "logs" / "events.jsonl")
    for doc in DOCS:
        if (source / doc).is_file():
            (sample / doc).write_text(sanitize((source / doc).read_text(), source.parent))
    for num, _, _ in PHASES:
        rows = (trim_row(r) for r in read_jsonl(source / "logs" / f"phase{num}.jsonl"))
        lines = [sanitize(json.dumps(r), source.parent) for r in rows if r]
        (sample / "logs" / f"phase{num}.jsonl").write_text("\n".join(lines) + "\n")
    print(f"Recorded {source} -> {sample}")


# ── replay ──────────────────────────────────────────────────
def _append(path: Path, row: Row) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _pause_for(row: Row) -> float:
    if row.get("type") == "result":
        return PAUSE["result"]
    blocks = (row.get("message") or {}).get("content") or []
    kinds = {b.get("type") for b in blocks if isinstance(b, dict)}
    if "tool_result" in kinds:
        return PAUSE["error"]
    return PAUSE["tool_use"] if "tool_use" in kinds else PAUSE["text"]


def _play_phase(sample: Path, target: Path, phase: str, speed: float) -> None:
    log = target / "logs" / f"phase{phase}.jsonl"
    log.touch()
    for row in read_jsonl(sample / "logs" / f"phase{phase}.jsonl"):
        _append(log, row)
        time.sleep(_pause_for(row) / speed)


def _run_finished(target: Path) -> bool:
    events = read_jsonl(target / "logs" / "events.jsonl")
    return any(e.get("event") in ("finish", "fail") for e in events)


def _prepare(target: Path, force: bool) -> None:
    """A finished (or failed) run may be replaced; a run that may still be live needs --force."""
    if (target / "logs").exists() and not force and not _run_finished(target):
        sys.exit(f"{target} holds a run that may still be in progress. Stop it, or pass --force.")
    shutil.rmtree(target / "logs", ignore_errors=True)
    for doc in DOCS:
        (target / doc).unlink(missing_ok=True)
    (target / "logs").mkdir(parents=True)


def play(sample: Path, target: Path, speed: float, force: bool = False) -> None:
    _prepare(target, force)
    events_log = target / "logs" / "events.jsonl"
    for event in read_jsonl(sample / "logs" / "events.jsonl"):
        row = {**event, "ts": int(time.time())}
        if row.get("event") == "run_start":
            row["replay"] = "true"
        if row.get("event") == "phase_end":
            doc = DOC_FOR_PHASE.get(str(row.get("phase")), "")
            if doc and (sample / doc).is_file():
                shutil.copy(sample / doc, target / doc)
        _append(events_log, row)
        print(f"  {row['event']} {row.get('phase', '')}".rstrip(), flush=True)
        if row.get("event") == "phase_start":
            _play_phase(sample, target, str(row.get("phase")), speed)
        time.sleep(PAUSE["event"] / speed)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--record", action="store_true", help="save the run in .factory/ as the sample")
    parser.add_argument("--speed", type=float, default=1.0, help="playback speed multiplier (default 1)")
    parser.add_argument("--force", action="store_true", help="overwrite a run already in .factory/")
    args = parser.parse_args(argv)
    if args.speed <= 0:
        parser.error("--speed must be positive")
    if args.record:
        record(FACTORY, SAMPLE)
        return
    print(f"Replaying {SAMPLE.name} into .factory/ at {args.speed}x. Ctrl+C to stop.")
    try:
        play(SAMPLE, FACTORY, args.speed, args.force)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
