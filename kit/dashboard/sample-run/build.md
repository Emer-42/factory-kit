# Build: issue #2 — GET /stats

## Files touched
- `tests/test_main.py` — added 4 tests (written first).
- `app/store.py` — added `Store.stats()` returning `{"players", "average"}` (average is `0.0` when empty, always a float).
- `app/main.py` — added `GET /stats` delegating to `STORE.stats()`.

## Red run (before implementation)
`pytest -q -p no:cacheprovider` → 4 failed, 5 passed.
Failures: `test_stats_empty` (404 != 200), `test_stats_counts_players_and_averages_totals`, `test_stats_average_is_float`, `test_stats_does_not_add_a_player` (all because `/stats` did not exist).

## Green run (after implementation)
`pytest -q -p no:cacheprovider` → 9 passed, 1 warning (anyio deprecation in starlette testclient, unrelated).

## Lint
`ruff check --no-cache app tests` → All checks passed!
