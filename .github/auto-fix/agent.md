# Auto-fix agent

`.github/auto-fix/run.ps1` gives you this file followed by one issue of `ZJLi2013/agent-loop`: its number, title, body
and comments. You are in a fresh worktree of `main`, inside a sandbox: you can edit files here and run Linux commands,
but not use the network, `git push`, `gh`, or Windows programs.

1. Decide whether the issue describes an agent-loop code defect you can reproduce from this checkout. Proposals and
   changes to rule, skill or prompt wording are not: they need a human decision, and no failing test proves them.
   If it is not, write `.auto-fix/stop.md` with what you checked and why, and stop.
2. Add a regression test under `tests/` (unittest, next to the tests of the component) that fails on the current code
   for the reason the issue states and passes once the defect is fixed. A defect that shows only on Windows gets a
   test guarded by `@unittest.skipUnless(sys.platform == "win32", ...)`; you cannot run it here, CI runs it on Windows.
   Run what you can with `python3 -m unittest discover -s tests`.
3. Fix the defect with the smallest change. Do not change `AI_POLICY.md` or anything under `.github/`.
4. Write `.auto-fix/title.txt`, one line stating the fixed behaviour in the style of `git log --oneline`, and
   `.auto-fix/body.md` following `.github/pull_request_template.md`:
   - `Closes #<number>` on the last line;
   - Evidence names the regression test and what it asserts; CI will show it failing on the test-only commit and
     passing after the fix, and `run.ps1` then removes the test, so it stays in the pull request's history only;
   - AI use: `Tool/model:` Codex, started by the maintainer's local auto-fix command; `Extent:` test and fix generated
     from the issue, not reviewed by a human before submission; `Human verification:` none yet.

   Keep local paths, host names and transcripts out of both files.
5. Do not commit. `run.ps1` commits your `tests/` changes first and the rest second, so the test must fail without
   the fix. It reverts the `tests/` commit after CI passes, so the fix must not depend on your test changes.
