## Problem

agent-loop plans one Goal at a time, and a Goal ends at DONE. Nothing above the Goal records the mainline question or the order of Goals, so every Goal boundary goes back to the human, and a Goal opened to work around a failure has nothing to be checked against.

Observed on one project over three days: 5 Goals, every one started by the human in conversation.

| Goal | Mainline / side | How it ended |
|---|---|---|
| walkthrough | mainline | reviewer `stop` |
| recipe ablation | mainline | reviewer `stop` |
| memory layer | mainline | one cell hit a gateway image cap; handed to the human |
| image delivery | side, opened by the image cap | reviewer `stop` |
| image window | side, opened by the image cap | `ask_human`, then paused by the human |

The memory-layer question already had enough valid pairs for a descriptive conclusion the night the cap was hit. It closed only after both side Goals, which cost about 3 GPU hours and an implementation commit without moving the mainline. No check compared them with the mainline until the human asked what problem they were solving.

When the human then wrote down the mainline and said "unattended", the worker wrote the next mainline Goal's plan and ran the independent plan review, and `init` was refused: `unattended after continue: only the reviewer's next task (win-ab-design) may start`. The named task belonged to the paused side Goal.

## Proposed layer

Policy / Skill, plus one Kernel guard.

## Why the current owner is insufficient

- `work-planning` writes the next 1–2 tasks and keeps later routes as candidates inside one Goal's plan; no document holds the sequence of Goals.
- `rules/agent-loop.mdc` stops at DONE when `task.md` has no active task. The task reviewer's `stop` means "Goal reached", and changing Goal is `ask_human`, so even a Goal already listed as a candidate is handed back.
- `harness/core.py` (the unattended branch of `init`) allows only the previous reviewer's `next_task` when the plan is not `approved`, and nothing after `stop`. Unattended self-approval writes `Plan Review: unreviewed`, so no new Goal can start unattended.
- `when-to-stop` hard stop 5 ("the mainline is not actually blocked by this problem") refers to a mainline that is not written anywhere. Once a side Goal opens, its own Goal sentence becomes the mainline, so the check never fires.

## Proposal

1. `task.md` gets a `## Mainline` section: one sentence for the mainline question and an ordered Goal list, each entry one line with its question, exit condition and status. It is written with the human when the first Goal is planned and approved at that Human Review Gate. Goals are listed, not tasks; tasks stay incremental.
2. `work-planning` Goal CLOSE: when the list has an aligned next Goal, the worker writes its plan document and runs plan review instead of stopping. A Goal outside the list, a reordering, or a significant trade-off still goes to the human, and reordering the list is a `replan`.
3. A Goal opened by a failure or infrastructure problem is marked as a side Goal with a budget and the mainline Goal it returns to. `when-to-stop` hard stop 5 compares against the list.
4. `core.py` guard: unattended `init` after `stop` is allowed for the first task of the next aligned mainline Goal when its plan review returned no `must` or `human` item. Everything else keeps the current guard.

## Acceptance evidence

- Tests for the guard: after `stop`, unattended init of the next aligned Goal's first task succeeds; a task of a Goal not in the list, a side Goal, or a plan with an open `must` / `human` item is refused with the current message; attended behaviour is unchanged. `pytest tests -q` passes.
- The owner texts state the mainline rule once and point to it elsewhere.

## Compatibility and migration

Projects without a `## Mainline` section behave as today. The guard only gains one allowed case.

---

AI use: drafted with Cursor (Claude Opus) from a case study another Cursor agent session wrote that night and from the current rule, skill and `harness/core.py` texts on `main`; the guard behaviour was checked against the code. The direction (a mainline layer and Goal hand-off) comes from that case study and has not been reviewed by the author yet.
