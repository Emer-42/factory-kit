"""The default phase prompts: a run never waits for a person."""

from __future__ import annotations

from tests.conftest import KIT


def test_plan_and_build_say_there_is_no_human_in_the_loop() -> None:
    for name in ("1-plan.md", "2-build.md"):
        text = (KIT / "prompts" / name).read_text()
        assert "no human in the loop" in text, name
        assert "Always deliver a change" in text or "always deliver" in text.lower(), name
