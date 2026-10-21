from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync-to-cursor.ps1"


@unittest.skipUnless(sys.platform == "win32", "sync-to-cursor.ps1 uses Windows junctions")
class SyncToCursorTest(unittest.TestCase):
    def test_second_checkout_retargets_existing_skill_junctions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "profile"
            skills_dest = profile / ".cursor" / "skills-cursor"
            local_skill = skills_dest / "local"
            local_skill.mkdir(parents=True)
            local_file = local_skill / "SKILL.md"
            local_file.write_text("user-owned skill", encoding="utf-8")
            checkouts = [root / "a", root / "b"]
            for checkout in checkouts:
                (checkout / "scripts").mkdir(parents=True)
                shutil.copyfile(SCRIPT, checkout / "scripts" / SCRIPT.name)
                (checkout / "rules").mkdir()
                (checkout / "harness").mkdir()
                for name in ("work-planning", "demo", "local"):
                    skill = checkout / "skills" / name
                    skill.mkdir(parents=True)
                    (skill / "SKILL.md").write_text(checkout.name, encoding="utf-8")

            def sync(checkout: Path) -> None:
                # Keep output as bytes: PowerShell 5.1 output need not use Python's locale codec.
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                     str(checkout / "scripts" / SCRIPT.name)],
                    env={**os.environ, "USERPROFILE": str(profile)},
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))

            def assert_targets(checkout: Path) -> None:
                for name in ("rules", "harness"):
                    self.assertEqual((profile / ".cursor" / name).resolve(),
                                     (checkout / name).resolve())
                for name in ("work-planning", "demo"):
                    linked = skills_dest / name
                    self.assertEqual(linked.lstat().st_reparse_tag, stat.IO_REPARSE_TAG_MOUNT_POINT)
                    self.assertEqual(linked.resolve(), (checkout / "skills" / name).resolve())
                self.assertEqual(local_skill.lstat().st_reparse_tag, 0)
                self.assertEqual(local_file.read_text(encoding="utf-8"), "user-owned skill")

            sync(checkouts[0])
            assert_targets(checkouts[0])
            sync(checkouts[1])
            assert_targets(checkouts[1])
            sync(checkouts[1])
            assert_targets(checkouts[1])
            for checkout in checkouts:
                for name in ("work-planning", "demo", "local"):
                    self.assertEqual(
                        (checkout / "skills" / name / "SKILL.md").read_text(encoding="utf-8"),
                        checkout.name,
                    )


if __name__ == "__main__":
    unittest.main()
