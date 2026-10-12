# Related projects and when to use them

[中文入口](../README.md) · [English entry](../en.md) · [Research context](../study/industry-practices.md)

Reviewed on **2026-10-12** using the first-party sources linked below. This is a comparison of purpose and
control boundaries, not an exhaustive feature inventory or performance benchmark. These projects operate
at different layers and can be complementary. Dynamic documentation can change after this review.

| Project / source | Primary workflow | Relationship to agent-loop |
|---|---|---|
| [Ralph — snarktank/ralph](https://github.com/snarktank/ralph) | Repeated fresh instances of Amp or Claude Code work through PRD items; Git, `progress.txt`, and `prd.json` retain state | A close reference for repeated execution and handoff. agent-loop organizes work around reviewed plans, project verifiers, and evidence-driven successor decisions. “Ralph” is a broader pattern; this row refers to this implementation |
| [Karpathy/autoresearch](https://github.com/karpathy/autoresearch) | Agent edits training code, runs a fixed-budget experiment, compares val_bpb, and keeps or discards the change | A focused experiment loop. agent-loop delegates the metric and experiment environment to each working project and provides reusable planning/review boundaries |
| [Aider — architect/editor mode](https://aider.chat/docs/usage/modes.html) | An architect proposes a solution and an editor turns it into file edits | A coding interaction and role-separation reference. agent-loop's reviewer operates at plan/task boundaries and evaluates evidence and next steps |
| [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) | A small model/environment/agent stack using shell actions and linear trajectories, with local and sandbox environment options | Useful when you want a compact agent implementation or research baseline. agent-loop is used around an existing host/worker and retains explicit project planning and verification state |
| [OpenHands / Agent Canvas](https://github.com/OpenHands/OpenHands) | Current README presents a self-hosted control center for coding agents, multiple execution backends, scheduled and webhook-triggered automations | Relevant when you need an always-on agent service and integrations. agent-loop's current scope is project iteration inside an existing host, with explicit limits on exited-session recovery |
| [LangGraph — Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | Checkpointers retain thread state; stores retain cross-thread information | A framework building block for applications with their own orchestration and recovery. agent-loop supplies an opinionated workflow for reviewed project iteration |

The [SWE-agent README](https://github.com/SWE-agent/SWE-agent) currently recommends mini-swe-agent as its
successor; the table therefore points new readers to mini-swe-agent. No benchmark claims from upstream
READMEs are reproduced here because this repository has not run a controlled comparison.

## agent-loop's scope

Choose agent-loop when you already use a coding agent and want a reusable discipline for iterative research
or engineering: a human-approved Goal, revision-bound tasks, project-owned acceptance checks, optional
independent review, and memory that carries evidence between iterations.

Its current enforced integration is Windows + Cursor. Portable CLI use does not provide complete control of
all tool calls or automatic session restart. Evaluate a host or supervisor with those capabilities when they
are requirements. The table does not imply that any listed project is a supported plug-in or verified integration.

External discovery/radar can remain an independent service. Its findings can enter a working project's plan
without embedding a tracker, model optimizer, or general automation platform in the harness.
