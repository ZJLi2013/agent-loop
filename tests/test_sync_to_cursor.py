from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync-to-cursor.ps1"


@unittest.skipUnless(sys.platform == "win32", "Cursor sync uses Windows junctions")
class SyncToCursorTest(unittest.TestCase):
    def test_second_checkout_retargets_existing_skill_junctions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile"
            skills_dest = profile / ".cursor" / "skills-cursor"
            local_skill = skills_dest / "local-skill" / "SKILL.md"
            local_skill.parent.mkdir(parents=True)
            local_skill.write_text("user content", encoding="utf-8")
            checkouts = [root / "checkout a", root / "checkout b"]
            for checkout in checkouts:
                (checkout / "scripts").mkdir(parents=True)
                shutil.copyfile(SCRIPT, checkout / "scripts" / SCRIPT.name)
                for name in ("rules", "harness", "skills/work-planning",
                             "skills/demo", "skills/local-skill"):
                    (checkout / name).mkdir(parents=True)
                for name in ("work-planning", "demo"):
                    (checkout / "skills" / name / "SKILL.md").write_text(
                        checkout.name, encoding="utf-8")

            env = dict(os.environ, USERPROFILE=str(profile))

            def sync(checkout: Path) -> None:
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                     "-File", str(checkout / "scripts" / SCRIPT.name)],
                    env=env, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            def assert_targets(checkout: Path) -> None:
                for name in ("rules", "harness"):
                    self.assertEqual((profile / ".cursor" / name).resolve(),
                                     (checkout / name).resolve())
                for name in ("work-planning", "demo"):
                    self.assertEqual((skills_dest / name).resolve(),
                                     (checkout / "skills" / name).resolve())
                self.assertEqual(local_skill.read_text(encoding="utf-8"), "user content")

            sync(checkouts[0])
            assert_targets(checkouts[0])
            sync(checkouts[1])
            assert_targets(checkouts[1])
            sync(checkouts[1])
            assert_targets(checkouts[1])
            for checkout in checkouts:
                for name in ("work-planning", "demo"):
                    self.assertEqual(
                        (checkout / "skills" / name / "SKILL.md").read_text(encoding="utf-8"),
                        checkout.name,
                    )


if __name__ == "__main__":
    unittest.main()
