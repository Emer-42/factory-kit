"""The test harness itself: stub claude and gh, and the problem-repo fixture."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_stubs_are_first_on_path_and_record_calls(tmp_path: Path, stub_env: dict[str, str]) -> None:
    stub_dir = Path(stub_env["STUB_DIR"])
    out = subprocess.run(
        ["claude", "-p", "hi"], env=stub_env, capture_output=True, text=True, check=True
    )
    assert (stub_dir / "argv.1").is_file()
    assert json.loads(out.stdout.strip().splitlines()[-1])["subtype"] == "success"

    body = tmp_path / "b.md"
    body.write_text("hello body\n")
    subprocess.run(
        ["gh", "pr", "create", "--body-file", str(body), "--title", "T"],
        env=stub_env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert (stub_dir / "pr.1.body").read_text() == "hello body\n"
    assert len((stub_dir / "gh.log").read_text().splitlines()) == 1
    assert len((stub_dir / "claude.log").read_text().splitlines()) == 1


def test_kit_repo_has_two_remotes(kit_repo: Path) -> None:
    remotes = subprocess.run(
        ["git", "remote"], cwd=kit_repo, capture_output=True, text=True, check=True
    )
    assert sorted(remotes.stdout.split()) == ["origin", "upstream"]
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=kit_repo, capture_output=True, text=True, check=True
    )
    assert status.stdout == ""
