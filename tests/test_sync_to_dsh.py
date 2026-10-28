from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync-to-dsh.ps1"


@unittest.skipUnless(os.name == "nt", "sync-to-dsh.ps1 uses PowerShell junctions")
class SyncToDshTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.checkout = Path(tmp.name) / "checkout"
        (self.checkout / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, self.checkout / "scripts")
        shutil.copy(SCRIPT.parent / "install-skills.py", self.checkout / "scripts")
        rules = self.checkout / "rules"
        rules.mkdir()
        (rules / "always.mdc").write_text(
            "---\ndescription: x\nalwaysApply: true\n---\nKeep task state in task.md.\n", encoding="utf-8")
        (rules / "conditional.mdc").write_text(
            "---\nalwaysApply: false\n---\nCONDITIONAL_ONLY\n", encoding="utf-8")
        self.skill = self.checkout / "skills" / "demo" / "SKILL.md"
        self.skill.parent.mkdir(parents=True)
        self.skill.write_text("---\nname: demo\ndescription: d\n---\nbody\n", encoding="utf-8")
        self.home = Path(tmp.name) / "dsh-home"

    def sync(self, home: Path | None = None) -> subprocess.CompletedProcess[str]:
        args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(self.checkout / "scripts" / "sync-to-dsh.ps1")]
        if home:
            args += ["-DshHome", str(home)]
        env = {k: v for k, v in os.environ.items() if k != "DSH_HOME"}
        env["USERPROFILE"] = str(self.checkout.parent)
        return subprocess.run(args, capture_output=True, text=True, env=env)

    def agents(self) -> str:
        return (self.home / "AGENTS.md").read_text(encoding="utf-8")

    def test_renders_always_rules_and_links_skills(self) -> None:
        self.assertEqual(self.sync(self.home).returncode, 0)
        agents = self.agents()
        self.assertIn("Keep task state in task.md.", agents)
        self.assertNotIn("CONDITIONAL_ONLY", agents)
        self.assertNotIn("alwaysApply", agents)
        linked = self.home / "skills" / "demo" / "SKILL.md"
        self.assertEqual(linked.read_bytes(), self.skill.read_bytes())

    def test_rerun_is_stable_and_preserves_user_content(self) -> None:
        (self.home / "skills" / "mine").mkdir(parents=True)
        (self.home / "skills" / "demo").mkdir()
        (self.home / "AGENTS.md").write_text("my own rules\n", encoding="utf-8")
        self.assertEqual(self.sync(self.home).returncode, 1)
        first = self.agents()
        self.assertEqual(self.sync(self.home).returncode, 1)
        self.assertEqual(self.agents(), first)
        self.assertEqual(first.count("Keep task state in task.md."), 1)
        backups = list(self.home.glob("AGENTS.md.backup-*"))
        self.assertEqual([b.read_text(encoding="utf-8") for b in backups], ["my own rules\n"])
        self.assertTrue((self.home / "skills" / "mine").is_dir())
        self.assertFalse((self.home / "skills" / "demo" / "SKILL.md").exists())
        self.assertEqual(list(self.home.glob("skills-backup-*")), [])
        self.assertEqual(sorted(p.name for p in (self.home / "skills").iterdir()), ["demo", "mine"])

    def test_missing_home_fails_with_message(self) -> None:
        result = self.sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DSH_HOME", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
