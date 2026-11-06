# Plan: issue #2 — GET /stats

## Requirement
Add `GET /stats` returning `{"players": <int>, "average": <float>}`, where `players` is the number of players in the store and `average` is the mean of their total points (`0` and `0.0` when the store is empty).

## Assumptions
- A "player" is any name with an entry in the store (i.e. anyone who has posted a score). Reading a total never creates a player (existing behaviour, kept).
- A player who posted only `0`-point scores still counts as a player (`points` allows `ge=0`), so they count toward `players` and drag the average down.
- `average` is the plain arithmetic mean of per-player totals, unrounded, always returned as a float (so `0.0` when empty, and e.g. `20.0` rather than `20`).
- No query parameters, no request body.

## Files to touch (all within SCOPE: `app/ tests/`)
- `tests/test_main.py` — new tests, written FIRST.
- `app/store.py` — add a `stats()` method (state and computation stay in the store; the endpoint holds no state).
- `app/main.py` — add the `GET /stats` endpoint, delegating to `STORE.stats()`.

## Tests to write first (in `tests/test_main.py`)
1. `test_stats_empty`: with an empty store, `GET /stats` returns 200 and `{"players": 0, "average": 0.0}`.
2. `test_stats_counts_players_and_averages_totals`: ana gets 10 then 5 (total 15) and leo gets 25 → `{"players": 2, "average": 20.0}`. This checks the average is over per-player totals, not per-score.
3. `test_stats_average_is_float`: the `average` value is a `float` even when the mean is whole.
4. `test_stats_does_not_add_a_player`: calling `STORE.total("ghost")` and then `GET /stats` still gives `players == 0`.

Run the tests first and confirm they fail, then implement.

## Implementation notes
- `Store.stats()` returns `{"players": len(self._scores), "average": sum(...) / len(...)}`, returning `0.0` for the average when there are no players.
- Endpoint annotated `-> dict`, functions under 30 lines, type hints everywhere.
- No new dependencies, no new modules.

## Out of scope
- Median, min/max, rounding or any other stats.
- Changes to `/scores` or `/leaderboard`.
- Persistence or a database.
- Any change to `requirements.txt`, `factory.conf`, `factory.sh`, `lib/`, `gates/`, `prompts/` or `AGENTS.md`.
