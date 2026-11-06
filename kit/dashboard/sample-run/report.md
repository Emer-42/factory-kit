# Check report: issue #2 (GET /stats)

## Tests
Command: `pytest -q -p no:cacheprovider`

```
.........                                                                [100%]
=============================== warnings summary ===============================
venv/lib/python3.11/site-packages/starlette/testclient.py:40
  venv/lib/python3.11/site-packages/starlette/testclient.py:40: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = typing.Callable[[], typing.ContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
9 passed, 1 warning in 0.15s
```

## Lint
Command: `ruff check --no-cache app tests`

```
All checks passed!
```

No fixes were needed. Only files named in the plan changed: `app/main.py`, `app/store.py`, `tests/test_main.py`.

## Security findings (diff vs main)

The diff adds `GET /stats` with no parameters or body, delegating to `STORE.stats()`. It does a read-only computation over in-memory state.

- Injection / eval / exec / shell calls: none.
- Unvalidated input: none. The endpoint takes no input.
- Secrets: none.
- Writes to files or logs: none.
- Division by zero: guarded (`if players else 0.0`).

Findings: none introduced by this diff.

Pre-existing, outside this diff (for the reviewer's information only):
- **low**: The in-memory store has no cap on distinct player names (`name` is limited to 40 chars, but the number of players is unbounded). `POST /scores` can grow memory without limit, and `/stats` iterates over all players on each call. This was not introduced by this change.
