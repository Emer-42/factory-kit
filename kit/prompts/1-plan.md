# Plan

Read GitHub issue #{{ISSUE}} with 'gh issue view {{ISSUE}} --repo {{UPSTREAM}}'. Read AGENTS.md and factory.conf.
Write .factory/plan.md: the requirement in one sentence, any assumptions (if the issue is ambiguous, pick the
narrowest reasonable reading and say so), the files to touch (only paths listed under SCOPE in factory.conf),
the tests to write FIRST, and what is out of scope. Do not write any code.
There is no human in the loop: nobody will answer questions or approve anything during this run.
If the issue conflicts with AGENTS.md, a gate in gates/ or SCOPE, choose the closest reading that respects
them, say so under the assumptions, and plan a change that can be delivered. Never plan to wait for a person.
Always deliver a change.
