"""Run Codex CLI as the reviewer, from the project root; on Windows through WSL."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

ARGS_ENV = "AGENT_LOOP_CODEX_ARGS"
HARNESS_PROMPT = ".harness/review/prompt.md"


def command(out: str | None) -> list[str]:
    codex = ["codex", "exec", "--skip-git-repo-check", "-s", "read-only" if out else "workspace-write"]
    codex += shlex.split(os.environ.get(ARGS_ENV, ""))
    if out:
        # Relative, so the path means the same file on both sides of WSL.
        codex += ["-o", Path(os.path.relpath(out)).as_posix()]
    codex.append("-")
    script = 'export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"; exec ' + shlex.join(codex)
    return (["wsl.exe", "--"] if os.name == "nt" else []) + ["bash", "-lc", script]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m adapters.codex_review", description=__doc__)
    parser.add_argument("--prompt", default=HARNESS_PROMPT, help=f"default: {HARNESS_PROMPT}")
    parser.add_argument("--out", help="write the final reply here and run read-only")
    args = parser.parse_args(argv)
    return subprocess.run(command(args.out), input=Path(args.prompt).read_bytes()).returncode


if __name__ == "__main__":
    sys.exit(main())
