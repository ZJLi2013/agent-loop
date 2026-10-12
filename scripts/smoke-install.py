"""Build sdist/wheel, install into a fresh venv, and exercise the public CLI.

Requires Python 3.11+, pip, and `python -m pip install build virtualenv`.
Build dependencies may require network access. No model or host hooks are used.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def run(argv: list[str], cwd: Path, env: dict[str, str], expected: int = 0) -> str:
    result = subprocess.run(
        argv, cwd=cwd, env=env, text=True, encoding="utf-8",
        capture_output=True, timeout=300,
    )
    if result.returncode != expected:
        raise RuntimeError(
            f"Command {argv!r}: expected exit {expected}, got {result.returncode}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryDirectory(prefix="agent-loop-install-") as directory:
        root = Path(directory)
        source = root / "source"
        source.mkdir()
        # The Python distribution contains the CLI and adapters. The full host
        # setup (rules, skills, scripts, pager) is distributed through Git checkout.
        for name in ("pyproject.toml", "README.md", "LICENSE"):
            shutil.copy2(repo / name, source / name)
        for name in ("harness", "adapters"):
            shutil.copytree(
                repo / name, source / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.log"),
            )
        print("Building sdist and wheel from a clean packaging directory...", flush=True)
        run([sys.executable, "-m", "build", str(source)], root, env)
        wheels = list((source / "dist").glob("*.whl"))
        if len(wheels) != 1 or len(list((source / "dist").glob("*.tar.gz"))) != 1:
            raise RuntimeError("Expected one sdist and one wheel")

        target = root / "venv"
        run([sys.executable, "-m", "virtualenv", "--no-periodic-update",
             "--app-data", str(root / "virtualenv-cache"), str(target)], root, env)
        binaries = target / ("Scripts" if os.name == "nt" else "bin")
        python = binaries / ("python.exe" if os.name == "nt" else "python")
        cli = binaries / ("agent-loop-harness.exe" if os.name == "nt" else "agent-loop-harness")
        run([str(python), "-m", "pip", "install", "--no-index", "--no-deps",
             str(wheels[0])], root, env)
        location = run([str(python), "-c",
                        "import harness, adapters; print(harness.__file__); print(adapters.__file__)"],
                       root, env)
        if not all(Path(line).resolve().is_relative_to(target.resolve())
                   for line in location.splitlines()):
            raise RuntimeError(f"Imports escaped the installed environment: {location}")
        run([str(python), "-c",
             "from harness.project import render_prompt; "
             "render_prompt('plan_review.md', plan_doc='p', task_doc='t', revision=1, "
             "checklist='', report_file='r'); "
             "render_prompt('task_review.md', task_id='t1', inputs='', extra='', "
             "decision_file='d', plan_name='p', plan_archive='a', plan_archive_name='a')"],
            root, env)
        run([str(cli), "--help"], root, env)

        project = root / "example"
        run([str(python), str(repo / "examples/minimal-project/prepare.py"), str(project)],
            root, env)

        def command(*args: str, expected: int = 0) -> dict:
            return json.loads(run([str(cli), *args], project, env, expected))

        command("init", "--task", "t1", "--plan-doc", "plan.md", "--",
                str(python), "-B", "-m", "unittest", "-v")
        failed = command("verify", expected=1)
        if failed["result"]["outcome"] != "fail":
            raise RuntimeError("The deliberately broken example did not fail verification")
        command("goal-review", "--decision", "continue", "--evidence",
                "Fractional mean test failed; replace integer division and keep the Goal.")
        code = project / "average.py"
        code.write_text(code.read_text().replace(" // ", " / "), encoding="utf-8")
        passed = command("verify")
        if passed["state"]["phase"] != "verified":
            raise RuntimeError("The repaired example was not verified")
        run_id = passed["state"]["last_run_id"]
        artifact = project / ".harness" / "artifacts" / run_id
        if not (artifact / "result.json").is_file():
            raise RuntimeError("Verification artifact missing")
        if "Ran 2 tests" not in (artifact / "stderr.log").read_text():
            raise RuntimeError("Verifier did not execute the example's two tests")

        # Exercise the installed completion gate after a post-verification edit.
        code.write_text(code.read_text() + "\n# Changed after verification.\n", encoding="utf-8")
        message = run([str(python), "-c",
                       "from pathlib import Path; from harness.core import completion_gate; "
                       "print(completion_gate(Path.cwd()))"], project, env)
        state = command("status")["state"]
        if state["last_outcome"] != "stale" or state["phase"] != "paused":
            raise RuntimeError(f"Changed workspace was not rejected: {message}")
        command("goal-review", "--decision", "continue", "--evidence",
                "Only a comment changed; rerun the same tests before completion.")
        command("verify")
        run([str(python), "-m", "pip", "check"], root, env)
        run([str(python), "-m", "pip", "uninstall", "-y", "agent-loop"], root, env)
        run([str(python), "-c", "import harness"], root, env, expected=1)
        print("PASS: sdist -> wheel -> isolated install -> fail -> repair -> verify -> stale evidence -> reverify -> uninstall")


if __name__ == "__main__":
    main()
