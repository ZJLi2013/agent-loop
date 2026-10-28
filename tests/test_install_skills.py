from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "install-skills.py"
_spec = importlib.util.spec_from_file_location("install_skills", SCRIPT)
install = sys.modules["install_skills"] = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(install)

PACK_TOML = """\
version = {version}
name = "my-pack"

[[skills]]
path = "skills/foo"
profiles = ["research"]

[[skills]]
repo = "some-project"
path = ".cursor/skills/bar"
profiles = ["ops"]
requires = ["remote-exec", "experiment-design"]

[[skills]]
path = "skills/gen-ppt"
profiles = ["ops"]

[[skills]]
path = "skills/needs-missing"
profiles = ["ops"]
requires = ["no-such-skill"]
"""


def skill(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(f"---\nname: {path.name}\ndescription: d\n---\n", encoding="utf-8")
    return path


def git(cwd: Path, *argv: str) -> None:
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *argv],
                   cwd=cwd, check=True, capture_output=True)


class InstallSkillsTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.checkout = self.tmp / "agent-loop"
        (self.checkout / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, self.checkout / "scripts")
        for name in ("work-planning", "remote-exec", "experiment-design", "gen-ppt"):
            skill(self.checkout / "skills" / name)
        self.pack = self.tmp / "my-pack"
        for name in ("foo", "gen-ppt", "needs-missing"):
            skill(self.pack / "skills" / name)
        self.write_pack()
        self.project = self.tmp / "some-project"
        self.bar = skill(self.project / ".cursor" / "skills" / "bar")
        self.home = self.tmp / "cursor-home"
        self.packs = self.tmp / "packs.txt"
        self.write_packs("ops")

    def write_pack(self, version: int = 1) -> None:
        (self.pack / "pack.toml").write_text(PACK_TOML.format(version=version), encoding="utf-8")

    def write_packs(self, profiles: str, *extra: str) -> None:
        lines = [f"pack {self.pack}", f"repo some-project {self.project}", f"profiles {profiles}", *extra]
        self.packs.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run_installer(self, *extra: str, host: str = "cursor") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.checkout / "scripts" / "install-skills.py"), "--host", host,
             "--home", str(self.home), "--packs", str(self.packs), *extra],
            capture_output=True, text=True)

    def target(self, path: Path) -> str | None:
        return install.link_target(path)

    @property
    def pack_dest(self) -> Path:
        return self.home / "skills"

    def test_inv1_name_owned_by_agent_loop_is_skipped(self) -> None:
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stdout, r"gen-ppt\s+my-pack\s+SKIPPED: name also owned by agent-loop")
        self.assertFalse(os.path.lexists(self.pack_dest / "gen-ppt"))
        self.assertEqual(self.target(self.home / "skills-cursor" / "gen-ppt"),
                         install.norm(self.checkout / "skills" / "gen-ppt"))
        self.assertEqual(self.target(self.pack_dest / "bar"), install.norm(self.bar))

    def test_inv1_plain_directory_and_foreign_link_are_kept(self) -> None:
        plain = self.pack_dest / "bar"
        plain.mkdir(parents=True)
        (plain / "mine.txt").write_text("keep", encoding="utf-8")
        elsewhere = skill(self.tmp / "elsewhere" / "foo")
        install.make_link(self.pack_dest / "foo", elsewhere)
        self.write_packs("ops,research")
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertIn("is a plain directory", result.stdout)
        self.assertIn("outside the registered sources", result.stdout)
        self.assertEqual((plain / "mine.txt").read_text(encoding="utf-8"), "keep")
        self.assertEqual(self.target(self.pack_dest / "foo"), install.norm(elsewhere))

    def test_inv1_same_name_in_two_packs_is_skipped(self) -> None:
        other = self.tmp / "team-pack"
        skill(other / "skills" / "foo")
        (other / "pack.toml").write_text(
            'version = 1\nname = "team"\n\n[[skills]]\npath = "skills/foo"\n', encoding="utf-8")
        self.write_packs("research", f"pack {other}")
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.count("name owned by more than one pack: my-pack, team"), 2)
        self.assertFalse(os.path.lexists(self.pack_dest / "foo"))

    def test_inv1_cursor_builtin_directory_blocks_a_pack_skill(self) -> None:
        (self.home / "skills-cursor" / "foo").mkdir(parents=True)
        self.write_packs("research")
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertIn("already exists", result.stdout)
        self.assertFalse(os.path.lexists(self.pack_dest / "foo"))

    def test_inv2_missing_requires_is_skipped(self) -> None:
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stdout, r"needs-missing\s+my-pack\s+SKIPPED: requires missing agent-loop skill no-such-skill")
        self.assertFalse(os.path.lexists(self.pack_dest / "needs-missing"))
        self.assertIn("ERROR: needs-missing", result.stderr)

    def test_inv3_only_links_into_registered_sources_are_removed(self) -> None:
        self.run_installer()
        mine = self.pack_dest / "mine"
        mine.mkdir()
        foreign = skill(self.tmp / "other-tool" / "foreign")
        install.make_link(self.pack_dest / "foreign", foreign)
        result = self.run_installer("--uninstall")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(os.path.lexists(self.pack_dest / "bar"))
        self.assertFalse(os.path.lexists(self.home / "skills-cursor" / "work-planning"))
        self.assertTrue(mine.is_dir())
        self.assertEqual(self.target(self.pack_dest / "foreign"), install.norm(foreign))
        self.assertTrue((self.bar / "SKILL.md").is_file())
        self.assertTrue((self.checkout / "skills" / "work-planning" / "SKILL.md").is_file())

    def test_inv4_profile_change_removes_unselected_links(self) -> None:
        self.run_installer()
        self.assertEqual(self.target(self.pack_dest / "bar"), install.norm(self.bar))
        self.write_packs("research")
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(os.path.lexists(self.pack_dest / "bar"))
        self.assertEqual(self.target(self.pack_dest / "foo"),
                         install.norm(self.pack / "skills" / "foo"))
        self.assertRegex(result.stdout, r"bar\s+my-pack\s+not selected by profiles")
        self.assertTrue((self.bar / "SKILL.md").is_file())

    def test_inv5_verify_lists_source_and_checkout_state(self) -> None:
        origin = self.tmp / "origin"
        shutil.move(str(self.project), str(origin))
        git(origin, "init", "-q")
        git(origin, "add", ".")
        git(origin, "commit", "-q", "-m", "one")
        (origin / "README").write_text("two", encoding="utf-8")
        git(origin, "add", ".")
        git(origin, "commit", "-q", "-m", "two")
        git(self.tmp, "clone", "-q", str(origin), str(self.project))
        git(self.project, "reset", "-q", "--hard", "HEAD~1")
        (self.bar / "SKILL.md").write_text("changed", encoding="utf-8")
        self.write_packs("ops")
        result = self.run_installer()
        self.assertRegex(result.stdout, r"work-planning\s+agent-loop\s+-> .*work-planning")
        self.assertRegex(result.stdout, r"bar\s+my-pack\s+-> .*bar\s+behind=1 dirty=yes")

    def test_inv6_unknown_pack_version_is_rejected(self) -> None:
        self.write_pack(version=2)
        self.write_packs("ops,research")
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertIn("unsupported pack.toml version 2", result.stderr)
        self.assertFalse(self.pack_dest.exists() and any(self.pack_dest.iterdir()))

    def check_pack_named_agent_loop(self, host: str, dest: Path) -> None:
        impostor = self.tmp / "impostor"
        for name in ("notes", "linked", "fine"):
            skill(impostor / "skills" / name)
        (impostor / "pack.toml").write_text(
            'version = 1\nname = "agent-loop"\n'
            + "".join(f'\n[[skills]]\npath = "skills/{n}"\n' for n in ("notes", "linked", "fine")),
            encoding="utf-8")
        self.packs.write_text(f"pack {impostor}\n", encoding="utf-8")
        (dest / "notes").mkdir(parents=True)
        (dest / "notes" / "mine.md").write_text("keep", encoding="utf-8")
        elsewhere = skill(self.tmp / "elsewhere" / "linked")
        install.make_link(dest / "linked", elsewhere)
        result = self.run_installer(host=host)
        self.assertEqual(result.returncode, 1)
        self.assertIn("is a plain directory", result.stdout)
        self.assertIn("outside the registered sources", result.stdout)
        self.assertEqual((dest / "notes" / "mine.md").read_text(encoding="utf-8"), "keep")
        self.assertEqual(self.target(dest / "linked"), install.norm(elsewhere))
        self.assertEqual(self.target(dest / "fine"), install.norm(impostor / "skills" / "fine"))
        self.assertEqual(list(self.home.glob("skills-backup-*")), [])

    def test_pack_named_agent_loop_cursor_gets_no_own_skill_rights(self) -> None:
        self.check_pack_named_agent_loop("cursor", self.home / "skills")

    def test_pack_named_agent_loop_dsh_gets_no_own_skill_rights(self) -> None:
        self.check_pack_named_agent_loop("dsh", self.home / "skills")

    def test_no_packs_file_installs_own_skills_as_before(self) -> None:
        self.packs = self.tmp / "absent.txt"
        own = self.home / "skills-cursor"
        (own / "gen-ppt").mkdir(parents=True)
        (own / "gen-ppt" / "copy.md").write_text("old copy", encoding="utf-8")
        stale = skill(self.tmp / "moved-checkout" / "work-planning")
        install.make_link(own / "work-planning", stale)
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in ("work-planning", "remote-exec", "experiment-design", "gen-ppt"):
            self.assertEqual(self.target(own / name), install.norm(self.checkout / "skills" / name))
        backups = list(self.home.glob("skills-backup-*/gen-ppt/copy.md"))
        self.assertEqual([b.read_text(encoding="utf-8") for b in backups], ["old copy"])
        self.assertEqual(self.run_installer().stdout.count("Linked skill"), 0)


if __name__ == "__main__":
    unittest.main()
