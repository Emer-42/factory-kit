"""scripts/check-problem-repo.sh: a problem repo is verified without tokens before publishing."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.conftest import ROOT
from tests.engine_helpers import commit_file, git_out

CHECK = ROOT / "scripts" / "check-problem-repo.sh"
EXEC = 0o755


@pytest.fixture
def problem(tmp_path: Path, stub_env: dict[str, str]) -> Path:
    repo = tmp_path / "problem"
    repo.mkdir()
    git_out(repo, stub_env, "init", "-q", "-b", "main")
    commit_file(repo, stub_env, "factory.conf", 'TEST_CMD="./check.sh"\nSCOPE="app/"\n')
    commit_file(repo, stub_env, "check.sh", "#!/usr/bin/env bash\nexit 0\n", EXEC)
    commit_file(repo, stub_env, "app/a.txt", "a\n")
    commit_file(repo, stub_env, ".gitignore", "venv/\n")
    subprocess.run(
        ["bash", str(ROOT / "sync.sh"), str(repo)], env=stub_env, check=True, capture_output=True
    )
    git_out(repo, stub_env, "add", "-A")
    git_out(repo, stub_env, "commit", "-q", "-m", "kit")
    return repo


def check(repo: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(CHECK), str(repo), *args], env=env, capture_output=True, text=True, timeout=120
    )


def line(out: subprocess.CompletedProcess[str], label: str) -> str:
    found = [l for l in out.stdout.splitlines() if l[5:].startswith(label)]
    assert found, f"no {label!r} line in:\n{out.stdout}\n{out.stderr}"
    return found[0]


def patch_adding(repo: Path, env: dict[str, str], tmp_path: Path, rel: str, name: str) -> Path:
    """A patch (made in a throwaway clone) that adds file `rel`."""
    clone = tmp_path / f"clone-{name}"
    subprocess.run(["git", "clone", "-q", str(repo), str(clone)], env=env, check=True)
    (clone / rel).parent.mkdir(parents=True, exist_ok=True)
    (clone / rel).write_text("planted\n")
    git_out(clone, env, "add", "-N", ".")
    patch = tmp_path / f"{name}.patch"
    patch.write_text(git_out(clone, env, "diff") + "\n")
    return patch


def test_clean_repo_passes(problem: Path, stub_env: dict[str, str]) -> None:
    out = check(problem, stub_env)
    assert out.returncode == 0, out.stdout + out.stderr
    assert out.stdout.rstrip().splitlines()[-1] == "check: all ok"


def test_tests_leaving_files_fail(problem: Path, stub_env: dict[str, str]) -> None:
    commit_file(
        problem, stub_env, "check.sh", "#!/usr/bin/env bash\ntouch .coverage\nexit 0\n", EXEC
    )
    out = check(problem, stub_env)
    assert out.returncode == 1
    assert line(out, "tests").startswith("FAIL") and ".coverage" in line(out, "tests")


def test_setup_runs_before_the_tests(problem: Path, stub_env: dict[str, str]) -> None:
    conf = (
        'TEST_CMD="test -f venv/ready"\nSCOPE="app/"\nSETUP="mkdir -p venv && touch venv/ready"\n'
    )
    commit_file(problem, stub_env, "factory.conf", conf)
    assert check(problem, stub_env).returncode == 0


def test_unsynced_kit_fails(problem: Path, stub_env: dict[str, str]) -> None:
    commit_file(problem, stub_env, "factory.sh", "#!/usr/bin/env bash\necho old\n", EXEC)
    out = check(problem, stub_env)
    assert out.returncode == 1 and line(out, "kit").startswith("FAIL")


def test_gate_failing_on_main_fails(problem: Path, stub_env: dict[str, str]) -> None:
    commit_file(problem, stub_env, "gates/bad.sh", "#!/usr/bin/env bash\necho nope\nexit 1\n", EXEC)
    out = check(problem, stub_env)
    assert (
        out.returncode == 1
        and line(out, "gates").startswith("FAIL")
        and "bad.sh" in line(out, "gates")
    )


def test_trip_patch_must_trip_the_named_gate(
    problem: Path, stub_env: dict[str, str], tmp_path: Path
) -> None:
    trip_x = '#!/usr/bin/env bash\ngrep -q "app/x.txt" <<<"$FACTORY_CHANGED" && { echo "x is not allowed"; exit 1; }\nexit 0\n'
    commit_file(problem, stub_env, "gates/no-x.sh", trip_x, EXEC)
    commit_file(problem, stub_env, "gates/zz-ok.sh", "#!/usr/bin/env bash\nexit 0\n", EXEC)
    x_patch = patch_adding(problem, stub_env, tmp_path, "app/x.txt", "x")
    y_patch = patch_adding(problem, stub_env, tmp_path, "app/y.txt", "y")

    assert check(problem, stub_env, "--trip", str(x_patch), "no-x.sh").returncode == 0
    wrong_gate = check(problem, stub_env, "--trip", str(x_patch), "zz-ok.sh")
    assert wrong_gate.returncode == 1 and "no-x.sh" in line(wrong_gate, "trip")
    no_trip = check(problem, stub_env, "--trip", str(y_patch), "no-x.sh")
    assert no_trip.returncode == 1 and line(no_trip, "trip").startswith("FAIL")
    # "review": the reviewer must reject, so no gate may stop it first
    assert check(problem, stub_env, "--trip", str(y_patch), "review").returncode == 0
    assert check(problem, stub_env, "--trip", str(x_patch), "review").returncode == 1


def test_check_runs_from_a_fresh_clone(problem: Path, stub_env: dict[str, str]) -> None:
    (problem / "check.sh").write_text("#!/usr/bin/env bash\nexit 1\n")  # uncommitted edit
    out = check(problem, stub_env)
    assert line(out, "clean").startswith("FAIL")  # the source repo is dirty...
    assert line(out, "tests").startswith("ok")  # ...but the tests ran on what is committed
