## Problem

After a rule-compliant CLOSE self-audit, an experiment directory still held 376 files (98 MB) of run output
next to the experiment document. The conclusion depended on two fields per episode (the final `terminated`
flag in `states.json` and the last `input_tokens` in the event stream); the per-run table holding them is
3.6 KB. Nothing read the rest after the verifier and the task reviewer finished.

| Retained | Files | Size | Read by the conclusion |
|---|---:|---:|---|
| Codex event streams | 10 | 96.2 MB | last token-usage event only |
| Per-step observation metadata | 268 | 0.28 MB | no |
| states / transcript / audit / recipe | 35 | 0.43 MB | final step of `states.json` only |
| Logs and text output | 54 | 0.85 MB | no |

Also:

- A run the document marks "not counted" (30.8 MB) was kept.
- The per-run table existed only inside the run directory; the document linked to it. Deleting the run
  directory would have deleted the evidence with it.
- Two sibling experiment directories in the same project have the same shape (about 360 MB in total).

The agent deleted png / npz as "intermediate" and kept json / log as "raw output". That split follows file
type, not use: the deleted per-step images and the kept per-step metadata are the same kind of record.

## Proposed layer

Policy / Skill.

## Why the current owner is insufficient

- `experiment-design` Phase 3 says "delete one-off scripts and intermediate files (keep raw output and
  logs)". It gives no test for raw versus intermediate, no location, and no retention period.
- `experiment-design` Phase 4, `work-planning` CLOSE and `design.md` all say raw runs and artifacts are
  never deleted / immutable. With no artifact store outside the working tree for detached remote runs,
  "immutable" becomes "kept beside the document forever".
- CLOSE only asks to link raw output, so the document points at the run directory instead of absorbing the
  per-run numbers.
- Deleting run output inside the workspace after the verifier is not an option either:
  `harness/fingerprint.py` hashes untracked files, so the deletion would make the verified evidence stale.

## Proposal

Policy wording only; no Kernel change.

1. Run output lives outside the experiment document directory: in the remote run directory, or in a
   scratch directory outside the repository or ignored by git. The document holds the per-run table the
   conclusion, verifier and reviewer read, plus the reproduction entry (script, commit, parameters).
2. CLOSE self-audit writes that table into the document, deletes runs the conclusion excludes, and moves
   any run output it finds in the document directory out of it.
3. After the task reviewer's decision lands (or after the verifier when no reviewer is configured), the
   task's run output is deleted. Sub-experiment documents stay immutable; "immutable" no longer covers run
   output.
4. `design.md`, `work-planning` and the record-lifecycle study note drop "raw runs / artifacts are never
   deleted" and point to the same rule.

## Acceptance evidence

- The four owner texts state the rule once (owner: `experiment-design`) and no longer say raw runs or
  artifacts are kept; a grep for the old phrases returns nothing.
- Replaying the rule on the case: the per-run table moves into the experiment document, the run
  directories are removed, the conclusion and its evidence are still readable from the document alone,
  and `git status` shows no untracked files under the experiment directory.
- `pytest tests -q` passes.

## Compatibility and migration

Skill and design text only. Existing projects keep their current run directories until their next task
CLOSE. A project that wants long-term raw evidence keeps it in an external store and links it.

Case study: `case_study/harness-vla-run-artifact-retention.md`.

---

AI use: drafted with Cursor (Claude Opus) from a file inventory of the experiment directory, the current
skill texts and `harness/fingerprint.py`; the counts come from a PowerShell inventory and were checked
against the experiment document.
