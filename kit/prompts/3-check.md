# Check

Read AGENTS.md, factory.conf and .factory/plan.md. Run the TEST_CMD and the LINT_CMD from factory.conf, exactly as
written. Then do a security pass on the diff ('git diff main'): injection, unvalidated input, secrets, unsafe
calls, writing data to files or logs. If tests or lint fail, fix them, but only in files the plan names.
Do NOT fix security findings: list each with a severity (critical, high, medium, low) so the reviewer decides.
Write .factory/report.md with the final test and lint output verbatim and the findings.
