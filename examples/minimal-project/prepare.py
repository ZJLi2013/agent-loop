"""Copy the intentionally failing example into a new, disposable project."""

import argparse
import shutil
import subprocess
from pathlib import Path


def prepare(destination: Path) -> None:
    source = Path(__file__).resolve().parent
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("average.py", "test_average.py", "plan.md"):
        shutil.copy2(source / name, destination / name)
    runtime = destination / ".agent-loop"
    runtime.mkdir()
    task = (source / "task.md").read_text(encoding="utf-8")
    # The copied task lives one level below the plan.
    (runtime / "task.md").write_text(
        task.replace("](plan.md", "](../plan.md"), encoding="utf-8"
    )
    (destination / ".gitignore").write_text(
        ".harness/\n.agent-loop/\n__pycache__/\n", encoding="utf-8"
    )
    # `init` lints the files changed since HEAD, so the example needs a first commit.
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=example", "-c", "user.email=example@localhost", "commit", "-qm", "example"]):
        subprocess.run(["git", *args], cwd=destination, check=True)
    print(f"Created example project: {destination.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    prepare(parser.parse_args().destination)
