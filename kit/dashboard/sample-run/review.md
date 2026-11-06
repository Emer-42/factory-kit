# Review — Issue #2: `GET /stats`

Reviewer inputs: `AGENTS.md`, `.factory/plan.md`, `.factory/report.md`, `git diff main`, and my own runs of `pytest -q`, `pytest -q --collect-only`, `ruff check .` and `git status --porcelain --untracked-files=all`.

## Diff vs plan

| Plan item | In diff | Notes |
|---|---|---|
| `StatsOut` pydantic model `{count: int, average: float}` in `app/main.py` | Yes | Matches assumption 2. |
| `GET /stats` handler that only delegates to the store | Yes | `return StatsOut(**STORE.stats())`. The endpoint holds no state. |
| `Store.stats()` in `app/store.py` (count and mean of per-player totals) | Yes | Empty store returns `0.0` with no division by zero (assumption 3). No rounding (assumption 4). |
| 4 tests in `tests/test_main.py` | Yes | The names and assertions match plan items 1 to 4 exactly. |

There is nothing in the diff that the plan does not list.

## Scope

- `git status` shows only `app/main.py`, `app/store.py` and `tests/test_main.py` as modified, with no untracked files. Everything is under `app/` and `tests/`.
- `factory.sh`, CI, `AGENTS.md`, `dashboard/`, `requirements.txt` and `README.md` are untouched. No new dependencies were added.
- No plan or review text appears in code comments. All new functions are well under 30 lines.

## Tests

- I ran `pytest -q` myself: **21 passed, 1 warning**. The warning is a third-party Starlette/anyio deprecation and has nothing to do with this diff. My result matches the report.
- `--collect-only` lists all 4 new tests: `test_stats_empty`, `test_stats_count_and_average`, `test_stats_uses_player_totals` and `test_stats_non_integer_average`.
- The tests check behavior, not implementation. Each one goes through the public HTTP interface (`POST /scores`, then `GET /stats`) and asserts on status and JSON. None of them call `Store.stats()` directly or inspect private state. `test_stats_uses_player_totals` pins the ambiguous assumption 1, and `test_stats_non_integer_average` guards against integer truncation.
- Isolation comes from the existing `setup_function`, which calls `STORE.reset()` before each test.
- I ran `ruff check .` myself: "All checks passed!"
- I could not verify the test-first order from the diff, because the working tree is uncommitted. Nothing contradicts it.

## Security

- The report lists 2 findings. Both are **low**, and there are no critical or high findings.
  1. Unauthenticated aggregate disclosure (player count). This exposure is negligible given the public `/leaderboard`, and auth is out of scope.
  2. O(n) computation over an unbounded store. The same problem already exists in `/leaderboard`, and rate limiting is out of scope.
- My own check of the diff: no eval/exec, no shell, no file I/O, and no new inputs. The endpoint takes no parameters, so no pydantic input model is needed, and the response is typed through `StatsOut`. I agree with the report's assessment.

## Non-blocking nits

- `float(average)` in `Store.stats()` is redundant, since `sum/count` and `0.0` are already floats. It is harmless.
- `Store.stats() -> dict` could return a `TypedDict` for tighter typing. This is optional.

## Decision

The diff matches the plan with no scope creep. The tests exist, check behavior through the API, and pass when run independently. Lint is clean, and there are no critical or high security findings.

VERDICT: APPROVE
