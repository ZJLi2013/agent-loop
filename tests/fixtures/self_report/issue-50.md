## Problem

After five closed experiment Goals, one project's `script/` directory holds 28 scripts. Eight are tracked infrastructure (`node_up.sh`, `run_episode.sh`, ...). The other 20 are untracked and named after a single experiment (`exp3_summarize.py`, `exp5_leak_check.py`, `img_ab_launch.sh`, `win_codex_run.sh`, ...):

| Owner Goal | State | Scripts | Other consumers |
|---|---|---:|---|
| recipe_ablation, memory_layer, image_delivery | closed | 12 | only their own experiment documents |
| (shared by the three above) | closed | 2 | `exp3_run_all.sh` was reused by all three Goals; it calls `exp3_restart_env.sh` |
| image_window | paused | 6 | its own experiment document |

Every CLOSE self-audit passed while these accumulated. The scripts that were reused across Goals stayed under their first experiment's name, and the one-off ones were never removed.

## Proposed layer

Policy / Skill.

## Why the current owner is insufficient

- `experiment-design` Phase 3 says "delete one-off scripts created by the current task; move scripts that will be reused to the formal directory, with a stable entry and tests". It does not say what makes a script one-off, so each task keeps its scripts "in case".
- The check runs at task CLOSE only. Scripts a later task of the same Goal reuses survive the first CLOSE, and `work-planning` Goal CLOSE has no step for scripts, so nothing removes them once the Goal closes.
- The run-output rule from #48 asks the document to keep a "reproduction entry (script, commit, parameters)". With untracked scripts there is no commit, so every one-off script becomes a reproduction entry the document links to and the audit keeps.

## Proposal

Policy wording only.

1. `experiment-design` classifies scripts by consumer: keep a script that a kept script calls or that the next approved task uses; promote a script reused across Goals to a stable entry without an experiment id, with a test; everything else is one-off. Before deleting a one-off script, the document records the parameters needed to reproduce the run (cells, seeds, key flags) and stops linking the script.
2. The reproduction entry becomes "the path of a kept script plus its parameters"; the document never depends on a one-off script.
3. `work-planning` Goal CLOSE deletes the one-off scripts that only this Goal's documents refer to. Scripts of a paused Goal stay until it closes.

## Acceptance evidence

- The owner texts state the classification once (`experiment-design`), Goal CLOSE has the deletion step, and the #48 wording no longer names scripts as reproduction entries; `pytest tests -q` passes.
- Replay on the case: the 12 one-off scripts of closed Goals leave `script/`, the paused Goal's 6 and the 2 cross-Goal scripts stay, and no experiment document links a removed script while the cells and parameters remain readable in the documents.

## Compatibility and migration

Skill text only. Projects clean their scripts at the next Goal CLOSE.

---

AI use: drafted with Cursor (Claude Opus) from a script inventory (tracked state, references from documents and other scripts) and the current skill texts; counts come from that inventory and were checked against the experiment documents.
