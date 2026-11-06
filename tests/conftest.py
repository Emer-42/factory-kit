"""Shared fixtures: a problem repo wired to a fake fork and upstream, and stub claude/gh on PATH.

Nothing here spends tokens or touches GitHub: the remotes are local bare repos and the
`claude` and `gh` on PATH are the scripts in tests/stubs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "kit"
STUBS = Path(__file__).resolve().parent / "stubs"

sys.path.insert(0, str(KIT))  # so `from dashboard import ...` works in panel tests

FACTORY_CONF = 'TEST_CMD="./check.sh"\nLINT_CMD="./lint.sh"\nSCOPE="app/ tests/"\n'
GITIGNORE = ".factory/*\n!.factory/.gitkeep\n"


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    out = subprocess.run(
        ["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


@pytest.fixture
def stub_env(tmp_path: Path) -> dict[str, str]:
    stub_dir = tmp_path / "stub"
    stub_dir.mkdir()
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = Test\n\temail = test@example.com\n[init]\n\tdefaultBranch = main\n"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith(("FACTORY_", "STUB_", "GIT_"))}
    env.update(
        PATH=f"{STUBS}{os.pathsep}{env['PATH']}",
        STUB_DIR=str(stub_dir),
        STUB_GH_USER="ana",
        STUB_GH_UPSTREAM="workshop/leaderboard-api",
        STUB_ISSUE_TITLE="Add stats",
        GIT_CONFIG_GLOBAL=str(gitconfig),
        GIT_CONFIG_NOSYSTEM="1",
    )
    return env


def _executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


@pytest.fixture
def kit_repo(tmp_path: Path, stub_env: dict[str, str]) -> Path:
    upstream = tmp_path / "upstream.git"
    fork = tmp_path / "fork.git"
    repo = tmp_path / "repo"
    for bare in (upstream, fork):
        subprocess.run(
            ["git", "init", "-q", "--bare", "-b", "main", str(bare)], env=stub_env, check=True
        )
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main", env=stub_env)
    if KIT.is_dir():
        shutil.copytree(KIT, repo, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    (repo / "factory.conf").write_text(FACTORY_CONF)
    _executable(repo / "check.sh", "#!/usr/bin/env bash\nexit 0\n")
    _executable(repo / "lint.sh", "#!/usr/bin/env bash\nexit 0\n")
    for rel, text in {
        "app/x.txt": "app\n",
        "tests/t.txt": "test\n",
        "AGENTS.md": "# Agents\n",
    }.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    (repo / ".factory").mkdir(exist_ok=True)
    (repo / ".factory" / ".gitkeep").write_text("")
    (repo / ".gitignore").write_text(GITIGNORE)
    git(repo, "add", "-A", env=stub_env)
    git(repo, "commit", "-q", "-m", "Initial commit", env=stub_env)
    for name, bare in (("origin", fork), ("upstream", upstream)):
        git(repo, "remote", "add", name, str(bare), env=stub_env)
        git(repo, "push", "-q", name, "main", env=stub_env)
    git(repo, "fetch", "-q", "upstream", env=stub_env)
    return repo


def run_factory(repo: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "factory.sh", *args], cwd=repo, env=env, capture_output=True, text=True, timeout=60
    )
