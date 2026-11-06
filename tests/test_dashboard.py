"""Tests for the read-only factory dashboard (dashboard/)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard import replay, server
from dashboard.state import build_state, phase_actions, read_jsonl

SAMPLE = Path(__file__).resolve().parent.parent / "kit" / "dashboard" / "sample-run"


def write_events(factory: Path, *events: dict) -> None:
    logs = factory / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))


def test_read_jsonl_skips_partial_and_blank_lines(tmp_path: Path) -> None:
    log = tmp_path / "x.jsonl"
    log.write_text('{"a": 1}\n\n{"b": 2}\n{"half": ')
    assert read_jsonl(log) == [{"a": 1}, {"b": 2}]
    assert read_jsonl(tmp_path / "missing.jsonl") == []


def test_empty_factory_dir_is_idle(tmp_path: Path) -> None:
    state = build_state(tmp_path)
    assert state["run"]["status"] == "idle"
    assert [p["status"] for p in state["phases"]] == ["pending"] * 4
    assert state["cost"] == 0


def test_recorded_sample_is_a_complete_approved_run() -> None:
    state = build_state(SAMPLE)
    assert state["run"]["status"] in {"committed", "pr"}  # re-recording a pushed run stays valid
    assert state["run"]["verdict"] == "APPROVE"
    assert [p["status"] for p in state["phases"]] == ["done"] * 4
    assert all(state["docs"].values())
    assert [g["after"] for g in state["gates"]] == ["2", "3", "final"]
    assert state["cost"] > 0


def test_failed_phase_and_reason_are_reported(tmp_path: Path) -> None:
    write_events(
        tmp_path,
        {"ts": 1, "event": "run_start", "issue": "7"},
        {"ts": 2, "event": "preflight", "ok": "true", "title": "T", "branch": "factory/issue-7"},
        {"ts": 3, "event": "phase_start", "phase": "1"},
        {"ts": 4, "event": "phase_end", "phase": "1"},
        {"ts": 5, "event": "phase_start", "phase": "2"},
        {"ts": 9, "event": "fail", "phase": "2", "reason": "phase 2 did not write .factory/build.md"},
    )
    state = build_state(tmp_path)
    assert [p["status"] for p in state["phases"]] == ["done", "failed", "skipped", "skipped"]  # kit: a stopped run never runs them
    assert state["run"]["status"] == "failed"
    assert state["run"]["reason"] == "phase 2 did not write .factory/build.md"
    assert state["run"]["ended"] == 9


def test_preflight_failure_is_shown_as_closed_gate(tmp_path: Path) -> None:
    write_events(
        tmp_path,
        {"ts": 1, "event": "run_start", "issue": "7"},
        {"ts": 2, "event": "fail", "phase": "", "reason": "working tree is not clean"},
    )
    run = build_state(tmp_path)["run"]
    assert (run["status"], run["preflight"]) == ("failed", "failed")


def test_phase_actions_extracts_tools_errors_and_text() -> None:
    rows = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "/repo/app/main.py"}},
            {"type": "thinking", "thinking": "hidden"},
            {"type": "text", "text": "Tests are red, as expected."},
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "is_error": True, "content": "1 failed"},
            {"type": "tool_result", "is_error": False, "content": "ok"},
        ]}},
        {"type": "user", "message": {"content": "plain string content"}},
    ]
    assert phase_actions(rows, root="/repo/") == [
        {"kind": "tool", "tool": "Edit", "detail": "app/main.py"},
        {"kind": "text", "detail": "Tests are red, as expected."},
        {"kind": "error", "detail": "1 failed"},
    ]


def test_state_endpoint_reads_factory_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FACTORY_DIR", str(SAMPLE))
    response = TestClient(server.app).get("/api/state")
    assert response.status_code == 200
    # Read from the sample, not hard-coded: re-recording a run with a new issue keeps main green.
    expected = build_state(SAMPLE)["run"]["title"]
    assert expected
    assert response.json()["run"]["title"] == expected


def test_index_serves_the_panel() -> None:
    response = TestClient(server.app).get("/")
    assert response.status_code == 200
    assert "Factory Control Panel" in response.text


def test_stream_sends_state_then_stops_on_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FACTORY_DIR", str(SAMPLE))
    monkeypatch.setattr(server, "POLL_SECONDS", 0)

    class OneShotRequest:
        def __init__(self) -> None:
            self.calls = 0

        async def is_disconnected(self) -> bool:
            self.calls += 1
            return self.calls > 2

    async def collect() -> list[str]:
        return [chunk async for chunk in server.state_events(OneShotRequest())]

    chunks = asyncio.run(collect())
    assert len(chunks) == 1  # unchanged state is not re-sent
    # "committed" for a FACTORY_NO_PUSH recording, "pr" for a pushed one (README prep step 4).
    assert json.loads(chunks[0].removeprefix("data: "))["run"]["status"] == build_state(SAMPLE)["run"]["status"]


def test_trim_row_keeps_only_what_the_dashboard_shows() -> None:
    row = {"type": "assistant", "message": {"id": "x", "usage": {}, "content": [
        {"type": "thinking", "thinking": "secret", "signature": "abc"},
        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "pytest -q"}},
    ]}}
    assert replay.trim_row(row) == {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q"}},
    ]}}
    assert replay.trim_row({"type": "system", "subtype": "init"}) is None


def test_sanitize_makes_paths_relative_and_hides_home(tmp_path: Path) -> None:
    line = f'{{"file_path": "{tmp_path}/app/main.py", "venv": "{Path.home()}/x"}}'
    assert replay.sanitize(line, tmp_path) == '{"file_path": "app/main.py", "venv": "~/x"}'


def test_replay_reproduces_the_sample_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(replay.time, "sleep", lambda _seconds: None)
    replay.play(SAMPLE, tmp_path, speed=1)
    state = build_state(tmp_path)
    assert state["run"]["status"] == build_state(SAMPLE)["run"]["status"]
    assert state["run"]["replay"] is True
    assert state["docs"] == build_state(SAMPLE)["docs"]


def test_replay_refuses_to_overwrite_a_run_in_progress(tmp_path: Path) -> None:
    write_events(tmp_path, {"ts": 1, "event": "run_start", "issue": "7"})
    with pytest.raises(SystemExit):
        replay.play(SAMPLE, tmp_path, speed=1)


def test_replay_replaces_a_finished_or_failed_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(replay.time, "sleep", lambda _seconds: None)
    write_events(tmp_path, {"ts": 1, "event": "run_start", "issue": "7"}, {"ts": 2, "event": "fail", "phase": "2", "reason": "x"})
    replay.play(SAMPLE, tmp_path, speed=1)
    assert build_state(tmp_path)["run"]["replay"] is True


def test_sanitize_collapses_pytest_relative_venv_paths(tmp_path: Path) -> None:
    line = "../../../../~/Downloads/demo-factory/venv/lib/python3.11/site-packages/x.py:40"
    assert replay.sanitize(line, tmp_path) == "venv/lib/python3.11/site-packages/x.py:40"


# ── kit: phase names from prompts, participant gates, draft PRs ─────────────
from tests.conftest import run_factory  # noqa: E402
from tests.engine_helpers import commit_file, script_phases  # noqa: E402


def test_phase_name_comes_from_prompt_heading(kit_repo: Path, stub_env: dict[str, str]) -> None:
    review = (kit_repo / "prompts" / "4-review.md").read_text().replace("# Review", "# Strict review", 1)
    commit_file(kit_repo, stub_env, "prompts/4-review.md", review)
    script_phases(stub_env)
    assert run_factory(kit_repo, {**stub_env, "FACTORY_NO_PUSH": "1"}, "1").returncode == 0
    names = [p["name"] for p in build_state(kit_repo / ".factory")["phases"]]
    assert names == ["Plan", "Build", "Check", "Strict review"]


def test_gate_events_are_listed(tmp_path: Path) -> None:
    write_events(
        tmp_path,
        {"ts": 1, "event": "run_start", "issue": "7"},
        {"ts": 2, "event": "scope", "after": "3", "ok": "true", "files": "app/x.py"},
        {"ts": 3, "event": "gate", "name": "no-deps.sh", "ok": "false"},
    )
    gate = build_state(tmp_path)["gates"][-1]
    assert (gate["event"], gate["name"], gate["ok"]) == ("gate", "no-deps.sh", "false")


def test_rejected_run_keeps_its_pr_url(tmp_path: Path) -> None:
    write_events(
        tmp_path,
        {"ts": 1, "event": "run_start", "issue": "7"},
        {"ts": 2, "event": "finish", "result": "rejected", "url": "https://x/pull/3"},
    )
    run = build_state(tmp_path)["run"]
    assert (run["status"], run["pr_url"]) == ("rejected", "https://x/pull/3")


def test_page_mentions_draft_pr_for_rejections() -> None:
    assert "draft PR opened" in TestClient(server.app).get("/").text
