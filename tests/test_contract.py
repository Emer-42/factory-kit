"""docs/run-contract.md is what the room board relies on; these tests keep the engine to it."""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.conftest import KIT, ROOT, run_factory
from tests.engine_helpers import REJECT, events, script_phases

DOC = ROOT / "docs" / "run-contract.md"
MARKER_KEYS = {"v", "ticket", "verdict", "stopped_by", "turns", "cost", "model", "tier"}


def doc() -> str:
    return DOC.read_text()


def fenced(label: str) -> list[str]:
    return re.findall(rf"```{label}\n(.*?)```", doc(), flags=re.S)


def recorded_pr(env: dict[str, str], n: int) -> tuple[list[str], str]:
    stub = Path(env["STUB_DIR"])
    return (stub / f"pr.{n}").read_bytes().decode().split("\0")[:-1], (
        stub / f"pr.{n}.body"
    ).read_text()


def test_marker_examples_in_doc_parse() -> None:
    examples = re.findall(r"<!-- factory-run (\{.*?\}) -->", doc())
    assert len(examples) >= 2
    for example in examples:
        assert set(json.loads(example)) == MARKER_KEYS


def test_real_prs_match_the_documented_conventions(
    kit_repo: Path, stub_env: dict[str, str]
) -> None:
    marker_re = re.compile(fenced("marker-regex")[0].strip())
    head_re = re.compile(fenced("head-regex")[0].strip())
    script_phases(stub_env)
    assert run_factory(kit_repo, stub_env, "1").returncode == 0
    subprocess_checkout_main(kit_repo, stub_env)
    script_phases(stub_env, phase4=REJECT)
    (Path(stub_env["STUB_DIR"]) / "count").unlink()
    assert run_factory(kit_repo, stub_env, "1").returncode == 1

    for n, verdict in ((1, "APPROVE"), (2, "REJECT")):
        args, body = recorded_pr(stub_env, n)
        flag = lambda name: args[args.index(name) + 1]  # noqa: E731
        assert head_re.match(flag("--head").split(":", 1)[1]), flag("--head")
        assert flag("--repo") == "workshop/leaderboard-api" and flag("--base") == "main"
        first = body.splitlines()[0]
        assert marker_re.match(first), first
        assert json.loads(marker_re.match(first).group(1))["verdict"] == verdict
        if verdict == "APPROVE":
            assert flag("--title") == "Add stats" and "--draft" not in args and "Closes #1" in body
        else:
            assert (
                flag("--title") == "[REJECTED] Add stats"
                and "--draft" in args
                and "Closes #1" not in body
            )


def test_every_emitted_event_is_documented() -> None:
    sources = [KIT / "factory.sh", *sorted((KIT / "lib").glob("*.sh"))]
    emitted = {
        name for path in sources for name in re.findall(r"\bemit ([a-z_]+)", path.read_text())
    }
    assert emitted >= {"run_start", "preflight", "phase_start", "finish"}
    for name in emitted:
        assert f"### `{name}`" in doc(), f"event {name} is not documented"


def test_real_events_only_use_documented_fields(kit_repo: Path, stub_env: dict[str, str]) -> None:
    documented: dict[str, set[str]] = {}
    for example in fenced("jsonl"):
        for line in example.splitlines():
            if line.strip():
                row = json.loads(line)
                documented.setdefault(row["event"], set()).update(row)
    script_phases(stub_env)
    assert run_factory(kit_repo, stub_env, "1").returncode == 0
    for row in events(kit_repo):
        extra = set(row) - documented[row["event"]]
        assert not extra, f"{row['event']} has undocumented fields {extra}"


def subprocess_checkout_main(repo: Path, env: dict[str, str]) -> None:
    import subprocess

    subprocess.run(["git", "checkout", "-q", "main"], cwd=repo, env=env, check=True)
