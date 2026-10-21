from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "skills" / "self-report" / "check_report.py"
TITLE = "[bug] sync-to-cursor.ps1 keeps skill junctions that point at another checkout"
BODY = """### Commit or release
45e05b9
### Layer
Adapter / Hook
### Reproduction
1. Clone the repository twice as `a/` and `b/`; set `USERPROFILE` to an empty temp directory.
2. `powershell -File a/scripts/sync-to-cursor.ps1`, then `powershell -File b/scripts/sync-to-cursor.ps1`.
3. `(Get-Item "$env:USERPROFILE\\.cursor\\skills-cursor\\work-planning").Target`
### Expected boundary
The second sync links every skill to `b/skills/`, as it does for `rules/` and `harness/`.
### Actual result and evidence
The target is still `a/skills/work-planning`: `scripts/sync-to-cursor.ps1:46-51` creates a junction only when the
path does not exist, and lines 39-44 prune only dead links.

AI use: found and reported by a Cursor agent (Claude Opus) through the self-report skill; not reviewed by a human before posting.
"""


class CheckReportTest(unittest.TestCase):
    def check(self, body: str, title: str = TITLE) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "body.md"
            path.write_text(body, encoding="utf-8")
            return subprocess.run(
                [sys.executable, "-B", str(CHECK), "--title", title, str(path)],
                capture_output=True, text=True, encoding="utf-8",
            )

    def assert_blocked(self, result: subprocess.CompletedProcess[str], category: str) -> None:
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(category, result.stdout)

    def test_clean_report_passes(self) -> None:
        result = self.check(BODY)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout, "")

    def test_credential_is_blocked(self) -> None:
        self.assert_blocked(self.check(BODY + "token=ghp_0123456789abcdefghijABCDEFGHIJ0123456789\n"), "credential")

    def test_local_path_is_blocked(self) -> None:
        body = BODY.replace("Clone the repository twice as `a/` and `b/`", "Clone into `C:\\Users\\alice\\work\\proj`")
        self.assert_blocked(self.check(body), "local path")

    def test_transcript_is_blocked(self) -> None:
        self.assert_blocked(self.check(BODY + "\n[assistant] I will now edit the rule.\n"), "transcript")

    def test_host_name_is_blocked(self) -> None:
        self.assert_blocked(self.check(BODY + "\nssh node-29.cluster.example.net\n"), "host name")

    def test_gpu_model_is_blocked(self) -> None:
        self.assert_blocked(self.check(BODY + "\nMeasured on MI308X.\n"), "gpu model")

    def test_title_is_checked(self) -> None:
        result = self.check(BODY, title="[bug] gate fails on node-29.cluster.example.net")
        self.assert_blocked(result, "title:1: host name")

    def test_missing_ai_use_is_blocked(self) -> None:
        self.assert_blocked(self.check(BODY.split("AI use:")[0]), "missing AI use")


if __name__ == "__main__":
    unittest.main()
