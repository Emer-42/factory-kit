# Build — Issue #2: Add a /stats endpoint

Implemented `.factory/plan.md` with TDD. Only the three files the plan names were changed.

## Files changed
- `tests/test_main.py`: added 4 tests, written first:
  `test_stats_empty`, `test_stats_count_and_average`, `test_stats_uses_player_totals`,
  `test_stats_non_integer_average`.
- `app/store.py`: added `Store.stats() -> dict`, which returns the count of players and the mean of their per-player totals. An empty store gives `{"count": 0, "average": 0.0}`. The result is always cast to `float`.
- `app/main.py`: added the `StatsOut` pydantic response model (`count: int`, `average: float`) and `GET /stats`, which returns `StatsOut(**STORE.stats())`.

No new dependencies. All functions are under 30 lines. No plan text was put in code comments.

## Red: `pytest -q` after adding the tests, before implementation
```
.................FFFF                                                    [100%]
FAILED tests/test_main.py::test_stats_empty - assert 404 == 200
FAILED tests/test_main.py::test_stats_count_and_average - AssertionError: ass...
FAILED tests/test_main.py::test_stats_uses_player_totals - AssertionError: as...
FAILED tests/test_main.py::test_stats_non_integer_average - KeyError: 'average'
4 failed, 17 passed, 1 warning in 0.17s
```
All 4 new tests failed for the expected reason: `/stats` did not exist yet and returned 404.

## Green: `pytest -q` after implementation
```
.....................                                                    [100%]
21 passed, 1 warning in 0.12s
```
The warning is a pre-existing starlette/anyio `DeprecationWarning` from `starlette/testclient.py` and has nothing to do with this change.

## Lint: `ruff check .`
```
All checks passed!
```

## Scope check: `git status --short`
```
 M app/main.py
 M app/store.py
 M tests/test_main.py
```
