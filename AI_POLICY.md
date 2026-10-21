# AI-assisted contributions

AI-assisted contributions are allowed, but the human contributor remains the author and is responsible for the
change.

## Required disclosure

Every pull request that used an AI tool must include:

```text
AI use
- Tool/model:
- Extent: planning / implementation / tests / documentation / review
- Human verification:
```

“AI-assisted” alone is not sufficient. State what the tool produced and what the contributor verified.

## Contributor responsibilities

The contributor must:

- understand and be able to explain the change without relying on the AI transcript;
- review and edit generated text and code before submission;
- run the relevant tests and report their actual output;
- verify integration with the surrounding state machine, policies, and adapters;
- remove prompt artifacts, speculative comments, and duplicated documentation.

Do not submit:

- private prompts, chat transcripts, credentials, internal repository names, hostnames, or unpublished baselines;
- AI-generated images, audio, or video;
- fabricated tests, benchmark results, citations, or claims;
- AI co-author trailers unless the repository history adopts such a convention.

The same review standard applies whether or not AI was used.

## Maintainer-configured automation

The maintainer runs two automations whose output is posted before a human reviews it:

- Agents following the `self-report` skill file issues labelled `from-agent`. The skill's check must pass before
  posting, and the issue ends with an `AI use:` line.
- The auto-fix agent described in `.github/auto-fix/agent.md` opens a pull request for an issue labelled `auto-fix`.
  The pull request carries the `auto-fix` label and its AI use section states that a cloud agent generated it and no
  human reviewed it before submission.

This output is exempt from reviewing and editing before submission; every other rule above applies. The maintainer
merges auto-fix pull requests and is responsible for the merged change.

