"""lib/gates.sh: participant gates run after phase 3 and before review."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import run_factory
from tests.engine_helpers import claude_calls, commit_file, events, last, script_phases

EXEC = 0o755


def rehearse(env: dict[str, str]) -> dict[str, str]:
    return {**env, "FACTORY_NO_PUSH": "1"}


def review_text(repo: Path) -> str:
    return (repo / ".factory" / "review.md").read_text()


def test_passing_gate_lets_review_run(kit_repo: Path, stub_env: dict[str, str]) -> None:
    commit_file(kit_repo, stub_env, "gates/ok.sh", "#!/usr/bin/env bash\nexit 0\n", EXEC)
    script_phases(stub_env)
    out = run_factory(kit_repo, rehearse(stub_env), "1")
    assert out.returncode == 0, out.stderr
    assert claude_calls(stub_env) == 4
    gate = last(kit_repo, "gate")
    assert (gate["name"], gate["ok"]) == ("ok.sh", "true")


def test_failing_gate_rejects_and_skips_review(kit_repo: Path, stub_env: dict[str, str]) -> None:
    gate = "#!/usr/bin/env bash\necho 'new dependency: left-pad'\nexit 1\n"
    commit_file(kit_repo, stub_env, "gates/no-deps.sh", gate, EXEC)
    script_phases(stub_env)
    out = run_factory(kit_repo, rehearse(stub_env), "1")
    assert out.returncode == 1
    assert claude_calls(stub_env) == 3
    review = review_text(kit_repo)
    assert "new dependency: left-pad" in review
    assert review.rstrip().splitlines()[-1] == "VERDICT: REJECT"
    assert last(kit_repo, "finish")["result"] == "rejected"
    assert (last(kit_repo, "gate")["name"], last(kit_repo, "gate")["ok"]) == ("no-deps.sh", "false")


def test_gate_sees_the_agents_diff_only(kit_repo: Path, stub_env: dict[str, str]) -> None:
    gate = '#!/usr/bin/env bash\nprintf "%s\\n" "$FACTORY_CHANGED" > .factory/changed.txt\nexit 0\n'
    commit_file(kit_repo, stub_env, "gates/list.sh", gate, EXEC)
    script_phases(stub_env)
    assert run_factory(kit_repo, rehearse(stub_env), "1").returncode == 0
    assert (kit_repo / ".factory" / "changed.txt").read_text().split() == ["app/x.txt"]


def test_gate_gets_base_and_root(kit_repo: Path, stub_env: dict[str, str]) -> None:
    gate = '#!/usr/bin/env bash\necho "$FACTORY_BASE $FACTORY_ROOT" > .factory/env.txt\nexit 0\n'
    commit_file(kit_repo, stub_env, "gates/env.sh", gate, EXEC)
    script_phases(stub_env)
    assert run_factory(kit_repo, rehearse(stub_env), "1").returncode == 0
    base, root = (kit_repo / ".factory" / "env.txt").read_text().split()
    assert len(base) == 40
    assert Path(root).resolve() == kit_repo.resolve()


def test_gate_not_executable_stops_with_chmod_hint(
    kit_repo: Path, stub_env: dict[str, str]
) -> None:
    commit_file(kit_repo, stub_env, "gates/a.sh", "#!/usr/bin/env bash\nexit 0\n", 0o644)
    script_phases(stub_env)
    out = run_factory(kit_repo, rehearse(stub_env), "1")
    assert out.returncode == 1
    assert "chmod +x gates/a.sh" in out.stderr  # stopped in preflight, before any phase


def test_gate_with_crlf_stops_with_hint(kit_repo: Path, stub_env: dict[str, str]) -> None:
    commit_file(kit_repo, stub_env, "gates/w.sh", "#!/usr/bin/env bash\r\nexit 0\r\n", EXEC)
    script_phases(stub_env)
    out = run_factory(kit_repo, rehearse(stub_env), "1")
    assert out.returncode == 1
    assert "Windows line endings" in out.stderr  # stopped in preflight, before any phase


def test_gate_timeout_stops_the_run(  # no skip: gates use a built-in watchdog, coreutils or not
    kit_repo: Path, stub_env: dict[str, str]
) -> None:
    conf = (kit_repo / "factory.conf").read_text() + "GATE_TIMEOUT=1\n"
    commit_file(kit_repo, stub_env, "factory.conf", conf)
    commit_file(kit_repo, stub_env, "gates/slow.sh", "#!/usr/bin/env bash\nsleep 5\n", EXEC)
    script_phases(stub_env)
    assert run_factory(kit_repo, rehearse(stub_env), "1").returncode == 1
    assert "timed out after 1s" in review_text(kit_repo)


def test_gates_run_in_name_order_and_stop_at_first_failure(
    kit_repo: Path, stub_env: dict[str, str]
) -> None:
    commit_file(kit_repo, stub_env, "gates/10-fail.sh", "#!/usr/bin/env bash\nexit 1\n", EXEC)
    commit_file(
        kit_repo, stub_env, "gates/20-mark.sh", "#!/usr/bin/env bash\ntouch .factory/ran\n", EXEC
    )
    script_phases(stub_env)
    assert run_factory(kit_repo, rehearse(stub_env), "1").returncode == 1
    assert not (kit_repo / ".factory" / "ran").exists()
    assert [e["name"] for e in events(kit_repo) if e["event"] == "gate"] == ["10-fail.sh"]


def test_readme_and_dotfiles_in_gates_are_skipped(kit_repo: Path, stub_env: dict[str, str]) -> None:
    commit_file(kit_repo, stub_env, "gates/README.md", "how to write a gate\n")
    commit_file(kit_repo, stub_env, "gates/.keep", "")
    script_phases(stub_env)
    assert run_factory(kit_repo, rehearse(stub_env), "1").returncode == 0
    assert [e for e in events(kit_repo) if e["event"] == "gate"] == []
