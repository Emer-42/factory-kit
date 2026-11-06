"""Organisers rehearse in their own repo (GitHub cannot fork your own repo): FACTORY_UPSTREAM."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.conftest import run_factory
from tests.engine_helpers import commit_file, script_phases


def pr_args(env: dict[str, str]) -> list[str]:
    return (Path(env["STUB_DIR"]) / "pr.1").read_bytes().decode().split("\0")[:-1]


def test_factory_upstream_skips_fork_detection(kit_repo: Path, stub_env: dict[str, str]) -> None:
    script_phases(stub_env)
    env = {**stub_env, "STUB_GH_NOT_FORK": "1", "FACTORY_UPSTREAM": "sgomezahumada/leaderboard-api"}
    out = run_factory(kit_repo, env, "1")
    assert out.returncode == 0, out.stderr
    args = pr_args(stub_env)
    assert args[args.index("--repo") + 1] == "sgomezahumada/leaderboard-api"
    assert args[args.index("--head") + 1].startswith("sgomezahumada:factory/issue-1-")


def test_without_factory_upstream_a_non_fork_still_stops(
    kit_repo: Path, stub_env: dict[str, str]
) -> None:
    out = run_factory(kit_repo, {**stub_env, "STUB_GH_NOT_FORK": "1"}, "1")
    assert out.returncode == 1 and "not a fork" in out.stderr


def test_doctor_suggests_setup_when_tests_fail(kit_repo: Path, stub_env: dict[str, str]) -> None:
    conf = (kit_repo / "factory.conf").read_text() + 'SETUP="make setup"\n'
    commit_file(kit_repo, stub_env, "factory.conf", conf)
    commit_file(kit_repo, stub_env, "check.sh", "#!/usr/bin/env bash\nexit 1\n", 0o755)
    out = subprocess.run(
        ["bash", "doctor.sh"], cwd=kit_repo, env=stub_env, capture_output=True, text=True
    )
    tests_line = [l for l in out.stdout.splitlines() if l.startswith("FIX  tests")]
    assert tests_line and "run  make setup  first" in tests_line[0]
