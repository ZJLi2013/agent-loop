# Security policy

## Supported versions

agent-loop is pre-1.0. Security fixes target the latest release and `main`; older snapshots may not receive
backports.

## Reporting a vulnerability

Use GitHub **Security → Report a vulnerability** to submit a private report. Do not include exploit details,
credentials, transcripts, or sensitive logs in a public Issue.

Relevant reports include:

- bypasses of timeout, budget, verification, review, or pause guards;
- command injection or unsafe process-tree handling;
- hooks reading or emitting unintended files, prompts, source, or secrets;
- path traversal outside the selected project;
- secret leakage through execution journals or hook output;
- installer/uninstaller changes that overwrite unrelated Cursor configuration.

Include the affected commit, OS, Python and Cursor versions, reproduction steps, expected boundary, and a minimal
sanitized proof. Maintainers will acknowledge the report as soon as practical and coordinate disclosure after a
fix is available.

## Trust boundary

Installing agent-loop creates user-level Cursor hooks and junctions. Those hooks execute local Python code in
every Cursor workspace. Review the checked-out commit before installation, pin versions in managed environments,
and do not run untrusted forks with production credentials.

