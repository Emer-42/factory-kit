"""Findings from the final whole-branch review, each pinned by a test (see the ledger)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from tests.conftest import KIT, ROOT, run_factory
from tests.engine_helpers import (
    REJECT,
    argv,
    claude_calls,
    commit_file,
    flag_values,
    git_out,
    last,
    script_phases,
)

EXEC = 0o755


def rehearse(env: dict[str, str]) -> dict[str, str]:
    return {**env, "FACTORY_NO_PUSH": "1"}


def branch(repo: Path, env: dict[str, str]) -> str:
    return git_out(repo, env, "branch", "--show-current")


def run_branches(repo: Path, env: dict[str, str]) -> list[str]:
    return git_out(repo, env, "branch", "--list", "factory/*", "--format=%(refname:short)").split()


# 1. Every run ends back on main, so the next fix is committed where the next run starts.
def test_rejected_rehearsal_returns_to_main(kit_repo: Path, stub_env: dict[str, str]) -> None:
    script_phases(stub_env, phase4=REJECT)
    out = run_factory(kit_repo, rehearse(stub_env), "1")
    assert out.returncode == 1
    assert branch(kit_repo, stub_env) == "main"
    assert len(run_branches(kit_repo, stub_env)) == 1
    assert "back on main" in out.stdout


def test_pushed_approval_returns_to_main(kit_repo: Path, stub_env: dict[str, str]) -> None:
    script_phases(stub_env)
    assert run_factory(kit_repo, stub_env, "1").returncode == 0
    assert branch(kit_repo, stub_env) == "main"
    assert git_out(kit_repo, stub_env, "status", "--porcelain") == ""


# 1. A broken gate fails in preflight, before any paid phase.
def test_non_executable_gate_fails_in_preflight(kit_repo: Path, stub_env: dict[str, str]) -> None:
    commit_file(kit_repo, stub_env, "gates/a.sh", "#!/usr/bin/env bash\nexit 0\n", 0o644)
    script_phases(stub_env)
    out = run_factory(kit_repo, rehearse(stub_env), "1")
    assert out.returncode == 1
    assert claude_calls(stub_env) == 0
    assert "chmod +x gates/a.sh" in out.stderr


def test_crlf_gate_fails_in_preflight_with_a_no_backup_fix(
    kit_repo: Path, stub_env: dict[str, str]
) -> None:
    commit_file(kit_repo, stub_env, "gates/w.sh", "#!/usr/bin/env bash\r\nexit 0\r\n", EXEC)
    out = run_factory(kit_repo, rehearse(stub_env), "1")
    assert out.returncode == 1 and claude_calls(stub_env) == 0
    assert "perl -pi -e" in out.stderr and "sed -i.bak" not in out.stderr


# 5. Editor and sed backups in gates/ are never run as gates.
def test_backup_files_in_gates_are_skipped(kit_repo: Path, stub_env: dict[str, str]) -> None:
    commit_file(kit_repo, stub_env, "gates/x.sh.bak", "#!/usr/bin/env bash\r\nexit 1\r\n", EXEC)
    commit_file(kit_repo, stub_env, "gates/y.sh~", "#!/usr/bin/env bash\nexit 1\n", EXEC)
    script_phases(stub_env)
    assert run_factory(kit_repo, rehearse(stub_env), "1").returncode == 0


# 2. A die's message reaches the fail event (the panel's Stopped card).
def test_die_reason_reaches_the_fail_event(kit_repo: Path, stub_env: dict[str, str]) -> None:
    script_phases(stub_env, phase1="true\n")
    run_factory(kit_repo, rehearse(stub_env), "1")
    assert "phase 1 did not write .factory/plan.md" in str(last(kit_repo, "fail")["reason"])


# 3. A stopped run keeps its work on the run branch and leaves main clean.
def test_stopped_run_parks_its_work_and_leaves_main_clean(
    kit_repo: Path, stub_env: dict[str, str]
) -> None:
    script_phases(stub_env, phase2="echo half > app/new.txt\necho more >> app/x.txt\n")
    out = run_factory(
        kit_repo,
        {**rehearse(stub_env), "STUB_RESULT_2": "error_max_turns", "STUB_EXIT_2": "1"},
        "1",
    )
    assert out.returncode == 1
    assert branch(kit_repo, stub_env) == "main"
    assert git_out(kit_repo, stub_env, "status", "--porcelain") == ""
    [run] = run_branches(kit_repo, stub_env)
    assert "app/new.txt" in git_out(kit_repo, stub_env, "show", "--name-only", "--format=", run)
    assert run in out.stderr


# 8. A turn limit is reported as a turn limit even when claude exits non-zero.
def test_turn_limit_with_nonzero_exit_says_so(kit_repo: Path, stub_env: dict[str, str]) -> None:
    script_phases(stub_env)
    out = run_factory(
        kit_repo,
        {**rehearse(stub_env), "STUB_RESULT_2": "error_max_turns", "STUB_EXIT_2": "1"},
        "1",
    )
    assert "phase 2 did not finish cleanly" in out.stderr
    assert "crashed" not in out.stderr


# 4. Runs work in a repo that does not ignore .factory/ itself.
def test_run_works_without_factory_in_gitignore(kit_repo: Path, stub_env: dict[str, str]) -> None:
    commit_file(kit_repo, stub_env, ".gitignore", "# nothing about .factory here\n")
    script_phases(stub_env)
    out = run_factory(kit_repo, rehearse(stub_env), "1")
    assert out.returncode == 0, out.stderr


# 4. The panel's bytecode never dirties a problem repo.
def test_panel_bytecode_is_ignored_after_sync(tmp_path: Path, stub_env: dict[str, str]) -> None:
    repo = tmp_path / "problem"
    repo.mkdir()
    git_out(repo, stub_env, "init", "-q", "-b", "main")
    commit_file(repo, stub_env, "README.md", "x\n")
    subprocess.run(
        ["bash", str(ROOT / "sync.sh"), str(repo)], env=stub_env, check=True, capture_output=True
    )
    (repo / "dashboard" / "__pycache__").mkdir()
    (repo / "dashboard" / "__pycache__" / "server.cpython-312.pyc").write_bytes(b"x")
    status = git_out(repo, stub_env, "status", "--porcelain", "--untracked-files=all")
    assert "__pycache__" not in status


# 14. Test output that is not ignored is named in preflight, not blamed on an agent.
def test_unignored_test_output_is_caught_in_preflight(
    kit_repo: Path, stub_env: dict[str, str]
) -> None:
    commit_file(
        kit_repo, stub_env, "check.sh", "#!/usr/bin/env bash\ntouch .coverage\nexit 0\n", EXEC
    )
    script_phases(stub_env)
    out = run_factory(kit_repo, rehearse(stub_env), "1")
    assert out.returncode == 1 and claude_calls(stub_env) == 0
    assert ".gitignore" in out.stderr and ".coverage" in out.stderr


# 6. Only the repo's committed settings apply, never the participant's local ones.
def test_only_project_settings_apply(kit_repo: Path, stub_env: dict[str, str]) -> None:
    script_phases(stub_env)
    assert run_factory(kit_repo, rehearse(stub_env), "1").returncode == 0
    args = argv(stub_env, 1)
    assert args[args.index("--setting-sources") + 1] == "project"


# 7. Agents cannot edit .git/.
def test_git_dir_is_protected(kit_repo: Path, stub_env: dict[str, str]) -> None:
    script_phases(stub_env)
    assert run_factory(kit_repo, rehearse(stub_env), "1").returncode == 0
    assert {"Edit(.git/**)", "Write(.git/**)"} <= set(
        flag_values(argv(stub_env, 2), "--disallowedTools")
    )


# 11. The printed retry keeps the title and the base.
def test_pr_retry_command_is_complete(kit_repo: Path, stub_env: dict[str, str]) -> None:
    script_phases(stub_env, phase4=REJECT)
    out = run_factory(kit_repo, {**stub_env, "STUB_GH_PR_FAIL": "1"}, "1")
    assert out.returncode == 1
    assert (
        "--base main" in out.stderr
        and "--title" in out.stderr
        and "[REJECTED] Add stats" in out.stderr
    )


# 10. Doctor probes Claude with the factory's model, and warns when phases have no time limit.
def test_doctor_probes_the_configured_model(kit_repo: Path, stub_env: dict[str, str]) -> None:
    subprocess.run(
        ["bash", "doctor.sh"], cwd=kit_repo, env=stub_env, capture_output=True, text=True
    )
    probe = [
        l
        for l in (Path(stub_env["STUB_DIR"]) / "claude.log").read_text().splitlines()
        if "reply ok" in l
    ]
    assert probe and "--model claude-sonnet-5-5" in probe[0]


def test_doctor_warns_without_a_timeout_command(kit_repo: Path, stub_env: dict[str, str]) -> None:
    out = subprocess.run(
        ["bash", "doctor.sh"], cwd=kit_repo, env=stub_env, capture_output=True, text=True
    )
    has_timeout = bool(
        shutil.which("timeout", path=stub_env["PATH"])
        or shutil.which("gtimeout", path=stub_env["PATH"])
    )
    warned = any(l.startswith("WARN phase time limit") for l in out.stdout.splitlines())
    assert warned != has_timeout


def test_doctor_flags_a_broken_gate(kit_repo: Path, stub_env: dict[str, str]) -> None:
    commit_file(kit_repo, stub_env, "gates/a.sh", "#!/usr/bin/env bash\nexit 0\n", 0o644)
    out = subprocess.run(
        ["bash", "doctor.sh"], cwd=kit_repo, env=stub_env, capture_output=True, text=True
    )
    assert any(
        l.startswith("FIX  gates: ") and "chmod +x gates/a.sh" in l for l in out.stdout.splitlines()
    )


# 13. The panel never shows a skipped phase as waiting, nor promises PRs only on APPROVE.
def test_unstarted_phase_of_a_finished_run_is_skipped(tmp_path: Path) -> None:
    from dashboard.state import build_state

    from tests.test_dashboard import write_events

    write_events(
        tmp_path,
        {"ts": 1, "event": "run_start", "issue": "7"},
        {"ts": 2, "event": "phase_start", "phase": "1"},
        {"ts": 3, "event": "phase_end", "phase": "1"},
        {"ts": 4, "event": "finish", "result": "rejected", "url": "https://x/pull/3"},
    )
    assert [p["status"] for p in build_state(tmp_path)["phases"]] == [
        "done",
        "skipped",
        "skipped",
        "skipped",
    ]


def test_panel_copy_matches_the_kit() -> None:
    page = (KIT / "dashboard" / "index.html").read_text()
    assert "opens only on APPROVE" not in page
    assert 'skipped: "Skipped"' in page


def test_retry_command_quotes_survive_a_shell(tmp_path: Path) -> None:
    title = """[REJECTED] it's "x" & $y `z`"""
    script = f"source '{KIT}/lib/github.sh'; shell_words printf '%s' --title \"$T\""
    words = subprocess.run(["bash", "-c", script], env={"T": title, "PATH": "/usr/bin:/bin"}, capture_output=True, text=True).stdout
    # Running the printed command must reproduce the exact title.
    echoed = subprocess.run(["bash", "-c", words.replace("--title ", "", 1)], capture_output=True, text=True).stdout
    assert echoed == title, words
