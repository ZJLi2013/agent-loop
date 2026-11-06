from __future__ import annotations

import os
import shlex
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from adapters import codex_review

ARGS = "-m some-model -c 'provider.base_url=\"https://example.test/a b\"'"


class CodexReviewTest(unittest.TestCase):
    def run_review(self, *argv: str) -> tuple[list[str], bytes, int]:
        with tempfile.TemporaryDirectory() as directory:
            prompt = Path(directory) / "提示 prompt.md"
            prompt.write_bytes("审查这个改动\n".encode("utf-8"))
            done = mock.Mock(returncode=3)
            with mock.patch.dict(os.environ, {codex_review.ARGS_ENV: ARGS}), mock.patch.object(
                codex_review.subprocess, "run", return_value=done
            ) as run:
                code = codex_review.main(["--prompt", str(prompt), *argv])
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["wsl.exe", "--"] if os.name == "nt" else ["bash", "-lc"])
        codex = shlex.split(command[-1].split("; exec ", 1)[1])
        return codex, run.call_args.kwargs["input"], code

    def test_harness_review_runs_workspace_write_with_the_prompt_on_stdin(self) -> None:
        codex, stdin, code = self.run_review()
        self.assertEqual(
            codex,
            ["codex", "exec", "--skip-git-repo-check", "-s", "workspace-write",
             "-m", "some-model", "-c", 'provider.base_url="https://example.test/a b"', "-"],
        )
        self.assertEqual(stdin.decode("utf-8"), "审查这个改动\n")
        self.assertEqual(code, 3)

    def test_free_form_review_runs_read_only_and_writes_the_reply(self) -> None:
        codex, _, _ = self.run_review("--out", "review out/回复.md")
        self.assertEqual(codex[4], "read-only")
        self.assertEqual(codex[-3:], ["-o", "review out/回复.md", "-"])


if __name__ == "__main__":
    unittest.main()
