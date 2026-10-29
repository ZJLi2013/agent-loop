## Problem and outcome

<!-- State the user-visible problem and the resulting behavior. -->

## Public guarantee

Which public guarantee does it maintain? See the [scope in design.md](https://github.com/ZJLi2013/agent-loop/blob/main/design.md#范围).

- [ ] 1. Declared task lifecycle
- [ ] 2. Installation, wiring and compatibility on supported hosts
- [ ] 3. This repository's release, contribution, security and defect reporting

## Layer

- [ ] Config / Profile
- [ ] Policy / Skill
- [ ] Adapter / Hook
- [ ] Kernel state, event, or guard
- [ ] Documentation only

Owner changed:

Why the current owner was insufficient:

## Evidence

<!-- Commands, exit codes, transition/guard tests, or reproducible output. -->

```text
python -m unittest discover -s tests -v
```

## Compatibility and migration

<!-- CLI, hook, rule, skill, config/state schema, install/uninstall, or "None". -->

## AI use

- Tool/model: None
- Extent: None
- Human verification: None

## Checklist

- [ ] The replaced path was removed; this does not create a second owner.
- [ ] Tests added to `tests/` pin a contract; a test that only proves this fix was removed before merge.
- [ ] User-facing docs and CHANGELOG are updated.
- [ ] No `.harness/`, project memory/task state, credentials, transcripts, private hosts, or unpublished data are included.
- [ ] AI use is disclosed according to `AI_POLICY.md`.
- [ ] I can explain and maintain this change without relying on an AI transcript.

