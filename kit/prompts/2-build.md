# Build

Read AGENTS.md, factory.conf and .factory/plan.md. Implement the plan with TDD: write the failing tests first,
run the TEST_CMD from factory.conf, exactly as written, to see them fail, then implement until they pass, then
run the LINT_CMD from factory.conf if it sets one. Touch only the files the plan names.
Write what you did, including the red and green test runs, to .factory/build.md.
There is no human in the loop: nobody will answer questions during this run, so always deliver the change
the plan describes. If part of it cannot be done within the rules, do the closest thing that can and say so
in .factory/build.md.
