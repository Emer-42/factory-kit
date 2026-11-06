"""lib/github.sh: push to the fork, open the PR upstream, carry the run marker and tier."""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.conftest import run_factory
from tests.engine_helpers import REJECT, commit_file, git_out, script_phases

MARKER = re.compile(r"^<!-- factory-run (\{.*\}) -->$")
EXEC = 0o755


def pr(env: dict[str, str], n: int = 1) -> tuple[list[str], str]:
    stub = Path(env["STUB_DIR"])
    args = (stub / f"pr.{n}").read_bytes().decode().split("\0")[:-1]
    return args, (stub / f"pr.{n}.body").read_text()


def value(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


def marker(body: str) -> dict[str, object]:
    match = MARKER.match(body.splitlines()[0])
    assert match, body.splitlines()[0]
    return json.loads(match.group(1))


def fork_branches(repo: Path, env: dict[str, str]) -> list[str]:
    heads = git_out(repo, env, "ls-remote", "--heads", "origin").splitlines()
    return [h.split("refs/heads/")[1] for h in heads if "factory/" in h]


def test_approve_pushes_to_fork_and_opens_pr_upstream(
    kit_repo: Path, stub_env: dict[str, str]
) -> None:
    script_phases(stub_env)
    out = run_factory(kit_repo, stub_env, "1")
    assert out.returncode == 0, out.stderr
    branches = fork_branches(kit_repo, stub_env)
    assert len(branches) == 1 and re.match(r"^factory/issue-1-\d{8}-\d{6}$", branches[0])
    args, body = pr(stub_env)
    assert value(args, "--repo") == "workshop/leaderboard-api"
    assert value(args, "--head") == f"ana:{branches[0]}"
    assert value(args, "--base") == "main"
    assert value(args, "--title") == "Add stats"
    assert "--draft" not in args
    assert marker(body) == {
        "v": 1,
        "ticket": 1,
        "verdict": "APPROVE",
        "stopped_by": None,
        "turns": 12,
        "cost": 0.4,
        "model": "claude-sonnet-5-5",
        "tier": 1,
    }
    assert "Closes #1" in body


def test_reject_opens_a_draft_titled_rejected(kit_repo: Path, stub_env: dict[str, str]) -> None:
    script_phases(stub_env, phase4=REJECT)
    out = run_factory(kit_repo, stub_env, "1")
    assert out.returncode == 1
    args, body = pr(stub_env)
    assert "--draft" in args
    assert value(args, "--title") == "[REJECTED] Add stats"
    meta = marker(body)
    assert (meta["verdict"], meta["stopped_by"]) == ("REJECT", "review")
    assert "Closes #1" not in body
    assert "Rejected run for #1 (not closing it)" in body


def test_gate_rejection_names_the_gate_in_the_marker(
    kit_repo: Path, stub_env: dict[str, str]
) -> None:
    commit_file(
        kit_repo, stub_env, "gates/no-deps.sh", "#!/usr/bin/env bash\necho nope\nexit 1\n", EXEC
    )
    script_phases(stub_env)
    assert run_factory(kit_repo, stub_env, "1").returncode == 1
    meta = marker(pr(stub_env)[1])
    assert (meta["stopped_by"], meta["tier"], meta["turns"]) == ("gate:no-deps.sh", 2, 9)


def test_scope_rejection_marker(kit_repo: Path, stub_env: dict[str, str]) -> None:
    script_phases(stub_env, phase2_extra="echo oops > README.md\n")
    assert run_factory(kit_repo, stub_env, "1").returncode == 1
    assert marker(pr(stub_env)[1])["stopped_by"] == "scope"


def test_prompt_change_is_tier_3(kit_repo: Path, stub_env: dict[str, str]) -> None:
    review = (kit_repo / "prompts" / "4-review.md").read_text() + "Be strict.\n"
    commit_file(kit_repo, stub_env, "prompts/4-review.md", review)
    script_phases(stub_env)
    assert run_factory(kit_repo, stub_env, "1").returncode == 0
    assert marker(pr(stub_env)[1])["tier"] == 3


def test_marker_and_title_survive_shell_characters(
    kit_repo: Path, stub_env: dict[str, str]
) -> None:
    title = 'Add "x" & $y `z`'
    script_phases(stub_env)
    out = run_factory(kit_repo, {**stub_env, "STUB_ISSUE_TITLE": title}, "1")
    assert out.returncode == 0, out.stderr
    args, body = pr(stub_env)
    assert value(args, "--title") == title
    assert marker(body)["ticket"] == 1


def test_rerun_gets_a_new_branch(kit_repo: Path, stub_env: dict[str, str]) -> None:
    script_phases(stub_env)
    assert run_factory(kit_repo, stub_env, "1").returncode == 0
    git_out(kit_repo, stub_env, "checkout", "-q", "main")
    (Path(stub_env["STUB_DIR"]) / "count").unlink()
    out = run_factory(kit_repo, stub_env, "1")
    assert out.returncode == 0, out.stderr
    assert len(set(fork_branches(kit_repo, stub_env))) == 2
    assert (Path(stub_env["STUB_DIR"]) / "pr.2").is_file()


def test_not_a_fork_stops_with_hint(kit_repo: Path, stub_env: dict[str, str]) -> None:
    out = run_factory(kit_repo, {**stub_env, "STUB_GH_NOT_FORK": "1"}, "1")
    assert out.returncode == 1
    assert "not a fork of a workshop repo" in out.stderr


def test_mentions_are_defused(kit_repo: Path, stub_env: dict[str, str]) -> None:
    approve = "printf '# Review\\nThanks @octocat.\\n\\nVERDICT: APPROVE\\n' > .factory/review.md\n"
    script_phases(stub_env, phase4=approve)
    assert run_factory(kit_repo, stub_env, "1").returncode == 0
    body = pr(stub_env)[1]
    assert "@​octocat" in body
    assert "@octocat" not in body


def test_missing_upstream_remote_is_added(kit_repo: Path, stub_env: dict[str, str]) -> None:
    git_out(kit_repo, stub_env, "remote", "remove", "upstream")
    script_phases(stub_env)
    run_factory(kit_repo, {**stub_env, "FACTORY_NO_PUSH": "1"}, "1")
    url = git_out(kit_repo, stub_env, "remote", "get-url", "upstream")
    assert url == "https://github.com/workshop/leaderboard-api.git"


def test_fork_is_named_explicitly_to_gh(kit_repo: Path, stub_env: dict[str, str], tmp_path: Path) -> None:
    # With an `upstream` remote, plain `gh repo view` resolves to upstream (no parent).
    git_out(kit_repo, stub_env, "config", f"url.{tmp_path / 'fork.git'}.insteadOf", "https://github.com/ana/x.git")
    git_out(kit_repo, stub_env, "remote", "set-url", "origin", "https://github.com/ana/x.git")
    script_phases(stub_env)
    assert run_factory(kit_repo, stub_env, "1").returncode == 0
    gh_log = (Path(stub_env["STUB_DIR"]) / "gh.log").read_text()
    assert "repo view ana/x --json parent" in gh_log
    assert value(pr(stub_env)[0], "--head").startswith("ana:")
