"""Helpers for driving factory.sh through the stub claude: scripted phases, events, argv."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

PLAN = "mkdir -p .factory && echo '# Plan' > .factory/plan.md\n"
BUILD = "echo more >> app/x.txt && echo '# Build' > .factory/build.md\n"
REPORT = "echo '# Report' > .factory/report.md\n"
APPROVE = "printf '# Review\\nLooks fine.\\n\\nVERDICT: APPROVE\\n' > .factory/review.md\n"
REJECT = "printf '# Review\\nTests are missing.\\n\\nVERDICT: REJECT\\n' > .factory/review.md\n"
DEFAULT_PHASES = {1: PLAN, 2: BUILD, 3: REPORT, 4: APPROVE}


def script_phases(env: dict[str, str], **overrides: str) -> None:
    """Write $STUB_DIR/phaseN.sh. Override a phase with phase2="..." (append to the default
    with phase2_extra="...")."""
    stub = Path(env["STUB_DIR"])
    for num, body in DEFAULT_PHASES.items():
        body = overrides.get(f"phase{num}", body) + overrides.get(f"phase{num}_extra", "")
        (stub / f"phase{num}.sh").write_text("set -e\n" + body)


def events(repo: Path) -> list[dict[str, object]]:
    path = repo / ".factory" / "logs" / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def last(repo: Path, name: str) -> dict[str, object]:
    return [e for e in events(repo) if e["event"] == name][-1]


def argv(env: dict[str, str], call: int) -> list[str]:
    raw = (Path(env["STUB_DIR"]) / f"argv.{call}").read_bytes().decode()
    return raw.split("\0")[:-1]


def flag_values(args: list[str], flag: str) -> list[str]:
    """Values after a variadic flag, up to the next --option or the -- separator."""
    start = args.index(flag) + 1
    values = []
    for value in args[start:]:
        if value.startswith("--"):
            break
        values.append(value)
    return values


def prompt_of(args: list[str]) -> str:
    return args[args.index("--") + 1]


def claude_calls(env: dict[str, str]) -> int:
    count = Path(env["STUB_DIR"]) / "count"
    return int(count.read_text()) if count.is_file() else 0


def git_out(repo: Path, env: dict[str, str], *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=True
    ).stdout.strip()


def commit_file(repo: Path, env: dict[str, str], rel: str, text: str, mode: int = 0o644) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    path.chmod(mode)
    git_out(repo, env, "add", "-A")
    git_out(repo, env, "commit", "-q", "-m", f"participant: {rel}")
