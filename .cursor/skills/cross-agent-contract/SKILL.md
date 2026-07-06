---
name: cross-agent-contract
description: >-
  Coordinate two agents/repos that depend on each other via a single shared markdown contract doc:
  a mainline consumer (agent-A, e.g. an app/pipeline) and a component/dependency (agent-B, e.g. a
  library/service). Maintains one shared source-of-truth doc (gaps table, consumer-driven API
  requests, pinned contract details, dated two-way handshake) plus a dated recheck note in each repo.
  Use when two agents/codebases must align an integration or API across repo boundaries, when the
  user mentions cross-agent / two-agent coordination, an integration/upstream doc, an API contract
  between repos, or "leave a recheck note / wait for the other agent / sync via md".
disable-model-invocation: true
---

# Cross-Agent Contract (md-based)

Two agents own two repos with a dependency edge:
- **Agent-A = consumer / mainline** (drives requirements; e.g. an app, pipeline, downstream).
- **Agent-B = component / dependency** (provides the capability; e.g. a library, service, backend).

They can't see each other's chat. They align **only through markdown**. This skill fixes *which*
doc, *where* it lives, *what* goes in it, and the *handshake* that keeps both sides unblocked.

## Core rules (non-negotiable)

1. **One shared contract doc = single source of truth.** All cross-repo agreements live there.
   Each repo's own docs only record *its own* landing and link back to the shared doc as SoT.
2. **Lives in the component (agent-B) repo**, but is **written from the consumer's (agent-A) needs**.
   Rationale: agent-B must change to satisfy agent-A; the asks belong next to the code that changes.
3. **Agent-neutral content only.** No repo-specific experiment logs, run IDs, file-line markers, or
   private jargon — the *other* agent must understand it standalone. Keep it contract-level.
4. **Explicit blocking direction.** Always state who is blocked on whom, right now.

## The shared doc structure

Author/maintain these sections (rename to fit, keep the spine):

```
# Upstream/Integration — <component> as <role> for <consumer>
> purpose / trigger / one-line current-capability status

## 1. Consumer usage      2-4 bullets ("what A asks B to answer")
## 2. Gaps table          per row: # | gap | impact | status(done/partial/not-started)
## 3. API proposals        consumer-driven, prioritized; mark stable contracts "do-not-change"
## 4. Consumer integration  brief; "details live in <consumer>'s own docs"
## 5. Landing order        ordered steps with done / next / todo
## <handshake block>       dated recheck points + each side's reply (see below)
```

Guidelines:
- **Gaps table is the heartbeat.** A status column (done / partial / not-started) lets either agent
  see the blocking frontier without reading prose.
- **API proposals come from the consumer's real needs**, prioritized, with a default + escape hatch.
  Tag any agreed-stable signature "do-not-change" so the other agent won't churn it.
- **Pin the hard contract details** that silently break integrations: units, frame/coordinate
  conventions, quaternion/array ordering, data layout, who owns which decision (e.g. which side
  filters/excludes inputs). One bullet each.

## The dated two-way handshake

End the shared doc with a handshake block. Each agent appends a **dated reply** when it reviews:

```
> **<agent-B> -> <agent-A> recheck points (<date>)**: (1) ... (2) ... (3) ...   <- B asks A to confirm
> **<agent-A> reply (<date>)**: reviewed; (1) confirmed ... (2) ...;
>   currently blocked on <side>: start when <items> ready; <consumer> first step = <concrete action>. Notify when ready.
```

Rules for the handshake:
- **Date every entry** (`YYYY-MM-DD`) so the latest state is unambiguous.
- The reviewing agent **confirms each contract point**, states **what it's blocked on**, and names its
  **concrete first action on unblock** — so the other side knows exactly what "ready" triggers.
- End with an explicit **"notify when ready"** so it's clear this is async.

## The per-repo recheck note (in each agent's own repo)

Besides the shared doc, leave a short **dated RECHECK note** in the relevant feature/design doc of
*your own* repo. It must:
- link to the shared doc as SoT (don't duplicate the contract);
- list what *this* repo is blocked on (which items from the other agent);
- name the **first step** to take when unblocked;
- state "until then, don't touch <area>".

Example (consumer side):

```
> **RECHECK note (<date>)**: reviewed contract (<key points> consistent), blocked on <agent-B>;
> start <featureN> when <items> ready. First step = <concrete action>. Until then, don't touch <area>.
```

## Workflow

```
- [ ] 1. Decide roles: who is consumer (A) / component (B)
- [ ] 2. Create/locate the shared doc in B's repo, written from A's needs
- [ ] 3. Fill: consumer usage -> gaps table(status) -> API proposals(priority) -> pinned contract -> landing order
- [ ] 4. Strip anything repo-specific (experiment logs, line markers, private jargon)
- [ ] 5. Append dated handshake: confirm contract, state blocker, name first action
- [ ] 6. Leave a dated RECHECK note in your own repo linking to the shared doc
- [ ] 7. Park and wait for the other agent's dated reply / notify; then act on first action
```

## Anti-patterns

- Two parallel docs (one per repo) drifting apart -> keep **one** shared SoT.
- Pasting experiment results / run logs into the shared doc -> other agent can't parse it.
- Undated handshake entries -> can't tell current state.
- Re-stating the full contract in your repo's note -> link instead; note only your landing + blocker.
- Silent assumptions on units/conventions/ownership -> pin them explicitly in the contract section.
