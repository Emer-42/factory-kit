# Plan — Issue #2: Add a /stats endpoint

## Requirement
Add `GET /stats` returning the count and the average of all scores currently in the leaderboard store.

## Source
Issue #2 body, verbatim: "Return count and average of all scores". No comments, no labels, no acceptance criteria.

## Assumptions (the issue is ambiguous; narrowest reasonable reading chosen)
1. **"Scores" means per-player totals, not individual submissions.** `app/store.py` keeps only
   `name -> accumulated points`; individual `POST /scores` submissions are not retained.
   Therefore:
   - `count` = number of distinct players in the store.
   - `average` = arithmetic mean of the per-player totals.
   The alternative reading (count/average of every submission) would require changing the
   store's data model to record each submission. That is a larger change than the issue
   asks for, so it is not done here.
   Example: `ana +10`, `ana +5`, `leo +30` gives `{"count": 2, "average": 22.5}`, not
   `{"count": 3, "average": 15.0}`.
2. **Response shape:** `{"count": int, "average": float}`. Field names come directly from the issue.
3. **Empty store:** returns `{"count": 0, "average": 0.0}` with status 200, not `null`/404.
   This avoids division by zero and keeps the type stable (`float`).
4. **No rounding:** `average` is the plain float mean. Values that are not exactly
   representable in binary floating point are left as is.
5. **No query parameters.** `/stats` takes no input, so no new pydantic input model is needed.
   A pydantic response model (`StatsOut`) is used for a typed, documented response.
6. **State stays in the store:** computation lives in a new `Store.stats()` method in
   `app/store.py`. The endpoint only delegates to it, per AGENTS.md ("State lives in
   `app/store.py` only").

## Files to touch (only `app/` and `tests/`)
- `tests/test_main.py`: add the tests below **first**.
- `app/store.py`: add `Store.stats() -> dict` (count and mean of `self._scores.values()`).
- `app/main.py`: add the `StatsOut` pydantic model and the `GET /stats` handler that returns `STORE.stats()`.

No new dependencies.

## Tests to write FIRST (in `tests/test_main.py`; they must fail before implementation)
1. `test_stats_empty`: with the store reset, `GET /stats` returns 200 and `{"count": 0, "average": 0.0}`.
2. `test_stats_count_and_average`: post `ana 10` and `leo 30`. `GET /stats` returns `{"count": 2, "average": 20.0}`.
3. `test_stats_uses_player_totals`: post `ana 10`, `ana 5`, `leo 30`. `GET /stats` returns `{"count": 2, "average": 22.5}`.
   This test pins assumption 1.
4. `test_stats_non_integer_average`: post `ana 1` and `leo 2`. `average == 1.5`, which checks the average is not truncated to an int.

The existing `setup_function` (which calls `STORE.reset()`) gives each test an isolated store.

## Out of scope
- Recording individual submissions or changing the store's data model.
- Other statistics (min, max, median, sum, standard deviation) and per-player stats.
- Filtering, pagination, caching, or query parameters on `/stats`.
- Rounding or formatting rules for `average`.
- Any change outside `app/` and `tests/`. That includes `dashboard/`, `factory.sh`, `reset.sh`, CI, `requirements.txt`, `README.md` and `AGENTS.md`.
- Persistence, auth, and rate limiting.

## Done when
- `pytest -q` passes, including the 4 new tests.
- `ruff check .` is clean.
- Functions stay under 30 lines, and no plan text appears in code comments.
