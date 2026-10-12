# Release guide

[Project](../en.md) · [Release notes](releases/v0.1.0.md) · [Contributing](../CONTRIBUTING.md)

The initial distribution is a **GitHub Release from tag `v0.1.0`**, marked as a pre-release. The full
checkout includes policies and installer scripts; the Python package contains the CLI and adapter code.
PyPI publication and an automatic publishing workflow are outside this release.

## 1. Prepare the release commit

Review the working tree before staging. Maintainer workspaces can contain unrelated edits, personal runtime,
and files with platform-specific line endings. Do not use `git add .` as a substitute for this review.

```sh
git status --short
git diff --stat
git diff --ignore-space-at-eol --stat
```

Verify `pyproject.toml` has version `0.1.0`. Immediately before releasing, move the intended entries from
`CHANGELOG.md`'s `Unreleased` section into `## [0.1.0] - YYYY-MM-DD`, using the actual release date. Keep an
empty `Unreleased` section for subsequent changes and update its comparison link to
`https://github.com/ZJLi2013/agent-loop/compare/v0.1.0...HEAD`; link the new version to its release page.
The prepared notes in `docs/releases/v0.1.0.md` are release body text, not evidence that publication occurred.

Inspect the publicly tracked file list and selected diff. Confirm that `.agent-loop/`, `.harness/`, local
host settings, credentials, transcripts, and private project material are absent. Git ignore rules do not
remove files that are already tracked. Review case studies for publication as well.

Stage the intended files explicitly, inspect `git diff --cached`, and commit through your normal contribution
process. Do not include unrelated changes merely because a release is being prepared.

## 2. Validate a fresh checkout

Use a disposable clone of the intended commit with Python 3.11+ and pip/venv support. In an active build venv:

```sh
python -m pip install build virtualenv
python -m unittest discover -s tests -v
python scripts/smoke-install.py
python -m pip install -e "tools/pager[dev]"
python -m pytest tools/pager/tests -q
python -m compileall -q harness adapters tools/pager/pager scripts/smoke-install.py examples/minimal-project
```

The installation smoke copies packaging inputs into a temporary source tree, builds the sdist and then the
wheel, installs into a fresh venv, and exercises the public CLI from outside the checkout. It checks failure,
repair, verification artifacts, stale-evidence rejection, reverification, and uninstall. It uses no model or
API key and does not install Cursor hooks. Build dependencies may require network access.

Check whitespace with `git diff --check`. When inspecting an existing CRLF working tree, use
`git -c core.whitespace=cr-at-eol diff --check` to distinguish CRLF from actual trailing spaces; do not
normalize unrelated files during release preparation.

Push/merge the release preparation through your normal workflow. Confirm that the **exact intended commit**
has passed all jobs in `.github/workflows/test.yml`: Windows/Ubuntu Python 3.11/3.13, package installation,
pager tests, and the Windows installer job. Locally passing Linux tests do not substitute for the Windows jobs.

## 3. Validate the real Windows host

CI's installer job runs in an isolated profile and checks links and configuration; it does not launch Cursor.
On a disposable Windows account/profile with a supported Cursor installation:

1. Install the CLI and follow the quickstart in a separate demo project.
2. Run `scripts/sync-to-cursor.ps1` from the trusted release checkout, then restart Cursor.
3. Add project memory templates, open the demo project, and have the agent read `.agent-loop/task.md`.
   Confirm memory-hook output is delivered through the real host event.
4. Before verification passes, check that the stop hook requests continued work; after a fresh successful
   verification, check that the completion gate permits completion. Check preCompact delivery if your host
   provides a way to trigger it. Record the host version and any untested events.
5. Run `scripts/uninstall-from-cursor.ps1`, restart Cursor, and confirm agent-loop entries are removed.
   Backed-up directories are restored manually if needed.

Use configured reviewer/pager smoke checks as well if the release claims their end-to-end integration has
been tested. List untested optional transports as such. Do not imply a shell-only test exercised a live host.

## 4. Check repository settings

- Enable GitHub Private Vulnerability Reporting so the path described in `SECURITY.md` is available.
- Check issue templates and the test badge on the default branch.
- Add a concise repository description and relevant topics such as `agent-harness`, `research`, and `developer-tools`.
- Review the release notes against the support actually validated. Avoid claims of broader host compatibility.

These are maintainer checks; local scripts cannot establish the remote settings or CI result.

## 5. Tag and create a draft release

The following commands are publication steps for the maintainer. Run them from the clean, tested release
commit after merging. They are not performed by the installation smoke or ordinary test workflow.

```sh
git status --short
git rev-parse HEAD
git tag --list v0.1.0
git tag -a v0.1.0 -m "agent-loop v0.1.0"
git push origin v0.1.0
gh release create v0.1.0 --verify-tag --draft --prerelease --title "v0.1.0 — Initial public release" --notes-file docs/releases/v0.1.0.md
```

Before `git tag`, require an empty working-tree status, verify HEAD is the tested commit, and require that
`v0.1.0` does not already exist. If it exists remotely, fetch and inspect it; do not overwrite a published tag.
`gh` must be installed and authenticated to the repository. GitHub automatically provides source archives
for the tag, which are sufficient for this release; no manually built binaries need to be attached.

Open the draft in GitHub, check the tagged quickstart and usage links, review the notes and pre-release flag,
and publish when ready. The equivalent final CLI action is:

```sh
gh release edit v0.1.0 --draft=false --prerelease
```

If using only the GitHub web UI, create the release from the already-pushed tag, paste the notes, mark it as
a pre-release, save a draft, and review before publishing.

## 6. After publishing

Follow the tagged quickstart once from a new clone, check the links and release assets, and triage early
installation and workflow feedback. Use `v0.1.1` for compatible fixes. For breaking configuration or state
changes before 1.0, document the migration and normally advance to `0.2.0`. Avoid moving existing release tags.
