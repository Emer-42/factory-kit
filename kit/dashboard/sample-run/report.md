# Report — Issue #2: `GET /stats`

Branch: `factory/issue-2` (working tree, compared against `main` with `git diff main`)
Files changed: `app/main.py`, `app/store.py`, `tests/test_main.py` (all named in `.factory/plan.md`)

## Test and lint status

Both passed on the first run, so no files were modified.

### `pytest -q` (verbatim)

```
.....................                                                    [100%]
=============================== warnings summary ===============================
venv/lib/python3.11/site-packages/starlette/testclient.py:40
  venv/lib/python3.11/site-packages/starlette/testclient.py:40: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = typing.Callable[[], typing.ContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
21 passed, 1 warning in 0.12s
```

The one warning comes from Starlette's test client running against the installed anyio version. It is in a third-party package, not in this diff.

### `ruff check .` (verbatim)

```
All checks passed!
```

## Security pass on `git diff main`

The diff adds a `StatsOut` response model, a `Store.stats()` method, a `GET /stats` handler with no parameters, and 4 tests.

| Check | Result |
|---|---|
| Injection (SQL, command, template) | None. There is no query language, no shell call and no templating. |
| Unvalidated input | None added. `/stats` accepts no path, query or body parameters. The response is typed through the `StatsOut` pydantic model. |
| Secrets | None. No credentials, tokens, keys or env reads appear in the diff. |
| Unsafe calls (`eval`, `exec`, `subprocess`, `pickle`, `os.system`) | None. |
| Writing data to files or logs | None. The diff does no file I/O and no logging. |

### Findings (not fixed, for the reviewer to decide)

| # | Severity | Location | Finding |
|---|---|---|---|
| 1 | low | `app/main.py:38-40` | **Unauthenticated aggregate disclosure.** `/stats` is public and returns the number of distinct players and their mean score. Because `/leaderboard?limit=100` is already public and unauthenticated, this adds very little exposure. It does reveal the total player count beyond the top 100, which the leaderboard does not show. Plan says auth is out of scope. |
| 2 | low | `app/store.py:19-23` (with existing `POST /scores`) | **O(n) computation over an unbounded store.** Each `/stats` call copies and sums every per-player total. The store has no cap on distinct names and `POST /scores` has no rate limit (both existed before this diff). A client can create many names and then call `/stats` repeatedly, which costs CPU and memory. `/leaderboard` already sorts the whole store (O(n log n)) on each call, so `/stats` does not make this worse. Rate limiting is out of scope per the plan. |

### Considered and ruled out

- **Concurrent mutation during `stats()`.** FastAPI runs sync handlers in a threadpool. `list(self._scores.values())` runs inside a single C-level call under the GIL on CPython, so a concurrent `add()` cannot raise "dictionary changed size during iteration." This would need review only if the app moved to free-threaded Python (3.13t+).
- **Float overflow in `sum / count`.** Totals are Python ints with no upper bound, but `points` is capped at 1000 per submission. Pushing the mean past about 1.8e308 would take an impossible number of requests.
- **Pre-existing, outside this diff:** `ScoreIn.name` has no character allowlist. If `dashboard/` renders names without escaping, that is a stored-XSS risk. `/stats` does not return names, so this diff is not affected. This note is for awareness only, not a finding against this PR.
