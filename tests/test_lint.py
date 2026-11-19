from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from harness import run
from harness.core import disable, initialize
from harness.errors import HarnessError
from harness.lint import LINT_ARGV, lint_changed

ON_PATH = mock.patch("harness.lint.shutil.which", return_value="/bin/agent-loop-harness")


class LintTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "verify.py").write_text("print('OK')\n", encoding="utf-8")
        (self.root / "old.md").write_text("# Old\n\n旧任务（在跑）\n", encoding="utf-8")
        self.git("init", "-q")
        self.commit()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=self.root, check=True, capture_output=True, text=True,
        ).stdout

    def commit(self) -> None:
        self.git("add", "-A")
        self.git("commit", "-qm", "x")

    def write(self, name: str, text: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def init(self, task: str = "t1", **kwargs: object) -> None:
        initialize(self.root, task_id=task, verifier_argv=[sys.executable, "verify.py"], **kwargs)

    def test_dead_links_are_reported(self) -> None:
        self.write("docs/a.md", "\n".join([
            "[ok](../old.md) [anchor](#x) [web](https://example.com/p)",
            "[gone](missing.md)",
            "[run](../.harness/tasks/t1/run.sh)",
            "[bad](https:///nohost)",
            "[ref]: ./also-missing.md",
            "`[code](missing-in-code.md)`",
        ]))
        self.git("add", "-A")

        problems = lint_changed(self.root)

        self.assertEqual(len(problems), 4, problems)
        for line, reason in ((2, "dead link"), (3, "link into .harness/"), (4, "malformed URL"), (5, "dead link")):
            self.assertTrue(any(p.startswith(f"docs/a.md:{line}: {reason}") for p in problems), problems)

    def test_untracked_docs_are_reported_until_added(self) -> None:
        self.write("exp/notes.md", "结论\n")
        self.write(".agent-loop/plan.md", "（在跑）\n")

        self.assertEqual(lint_changed(self.root), ["exp/notes.md: not tracked by git"])
        self.git("add", "exp/notes.md")
        self.assertEqual(lint_changed(self.root), [])

    def test_leftover_wording_on_lines_this_task_wrote(self) -> None:
        self.write("old.md", "# Old\n\n旧任务（在跑）\n\n加 96 个初态（在跑）\n")

        problems = lint_changed(self.root)

        self.assertEqual(len(problems), 1, problems)
        self.assertTrue(problems[0].startswith("old.md:5: leftover '在跑'"))

    def test_legitimate_leftover_words_pass(self) -> None:
        self.write("old.md", "\n".join([
            "# Old", "", "旧任务（在跑）", "",
            "词表含 `TODO` 与 `在跑`。",
            "容器在跑时不能删 <!-- lint: allow -->",
            "```", "TODO: code sample", "```",
        ]))

        self.assertEqual(lint_changed(self.root), [])

    def test_wrapper_runs_the_verifier_only_when_lint_passes(self) -> None:
        argv = ["--root", str(self.root), "lint", "--changed", "--", sys.executable, "-c", "raise SystemExit(3)"]
        self.assertEqual(run.main(argv), 3)

        self.write("new.md", "[gone](missing.md)\n")
        marker = self.root / "ran"
        argv[-1] = f"open({str(marker)!r}, 'w')"
        with redirect_stderr(io.StringIO()) as err:
            self.assertEqual(run.main(argv), 1)
        self.assertFalse(marker.exists())
        self.assertIn("lint: new.md: not tracked by git", err.getvalue())

    def test_init_prepends_lint_without_locking_it(self) -> None:
        self.init(lint=False)
        off = json.loads((self.root / ".harness" / "config.json").read_text(encoding="utf-8"))
        disable(self.root)
        with ON_PATH:
            self.init("t2", lint=True)
        on = json.loads((self.root / ".harness" / "config.json").read_text(encoding="utf-8"))

        self.assertEqual(off["lint"], {"enabled": False})
        self.assertEqual(on["verifier"]["argv"], [*LINT_ARGV, "--", *off["verifier"]["argv"]])
        self.assertEqual(on["verifier"]["files"], off["verifier"]["files"])
        self.assertEqual(on["lint"]["base"], self.git("rev-parse", "HEAD").strip())

    def test_base_stays_at_init_and_moves_with_the_next_init(self) -> None:
        with ON_PATH:
            self.init(lint=True)
        self.write("doc.md", "[gone](missing.md)\n")
        self.commit()

        self.assertEqual(len(lint_changed(self.root)), 1)
        disable(self.root)
        with ON_PATH:
            self.init("t2", lint=True)
        config = json.loads((self.root / ".harness" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["lint"]["base"], self.git("rev-parse", "HEAD").strip())
        self.assertEqual(lint_changed(self.root), [])

    def test_failed_lint_precheck_leaves_runtime_unchanged(self) -> None:
        self.init(lint=False)
        disable(self.root)
        files = [self.root / ".harness" / name for name in ("config.json", "state.json")]
        before = [path.read_bytes() for path in files]
        with tempfile.TemporaryDirectory() as bare:
            for root, which in ((self.root, None), (Path(bare), "/bin/agent-loop-harness")):
                with self.subTest(root=root), mock.patch("harness.lint.shutil.which", return_value=which):
                    with self.assertRaises(HarnessError):
                        initialize(root, task_id="t2", verifier_argv=[sys.executable, "verify.py"], lint=True)
            self.assertFalse((Path(bare) / ".harness").exists())
        self.assertEqual([path.read_bytes() for path in files], before)


if __name__ == "__main__":
    unittest.main()
