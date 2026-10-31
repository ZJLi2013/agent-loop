from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        self.assertRegex(result.stdout, r"needs-missing\s+my-pack\s+SKIPPED: requires no-such-skill, which is not installable")
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
        self.write_pack(version=3)
        self.write_packs("ops,research")
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertIn("unsupported pack.toml version 3", result.stderr)
        self.assertFalse(self.pack_dest.exists() and any(self.pack_dest.iterdir()))

    def test_pack_named_agent_loop_gets_no_own_skill_rights(self) -> None:
        for host in ("cursor", "dsh"):
            with self.subTest(host=host):
                self.setUp()
                dest = self.home / "skills"
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

    def test_no_packs_file_links_own_skills_and_reports_a_plain_copy(self) -> None:
        self.packs = self.tmp / "absent.txt"
        own = self.home / "skills-cursor"
        (own / "gen-ppt").mkdir(parents=True)
        (own / "gen-ppt" / "copy.md").write_text("old copy", encoding="utf-8")
        stale = skill(self.tmp / "moved-checkout" / "work-planning")
        install.make_link(own / "work-planning", stale)
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stdout, r"gen-ppt\s+agent-loop\s+SKIPPED: .* is a plain directory")
        self.assertEqual((own / "gen-ppt" / "copy.md").read_text(encoding="utf-8"), "old copy")
        self.assertEqual(list(self.home.glob("skills-backup-*")), [])
        for name in ("work-planning", "remote-exec", "experiment-design"):
            self.assertEqual(self.target(own / name), install.norm(self.checkout / "skills" / name))
        self.assertEqual(self.run_installer().stdout.count("Linked skill"), 0)


RULE_PACK_TOML = """\
version = {version}
name = "rule-pack"

[[rules]]
path = "rules/z.mdc"

[[rules]]
path = "rules/ops-only.mdc"
profiles = ["ops"]
"""


def rule(path: Path, always: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    flag = "true" if always else "false"
    path.write_text(f"---\ndescription: d\nalwaysApply: {flag}\n---\n\n{path.stem.upper()}\n", encoding="utf-8")
    return path


class InstallRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.checkout = self.tmp / "agent-loop"
        (self.checkout / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, self.checkout / "scripts")
        skill(self.checkout / "skills" / "work-planning")
        rule(self.checkout / "rules" / "a.mdc")
        rule(self.checkout / "rules" / "b.mdc", always=False)
        self.pack = self.tmp / "rule-pack"
        rule(self.pack / "rules" / "z.mdc")
        rule(self.pack / "rules" / "ops-only.mdc")
        self.write_pack()
        self.home = self.tmp / "home"
        self.packs = self.tmp / "packs.txt"
        self.write_packs("")

    def write_pack(self, version: int = 2) -> None:
        (self.pack / "pack.toml").write_text(RULE_PACK_TOML.format(version=version), encoding="utf-8")

    def write_packs(self, profiles: str, *extra: str) -> None:
        self.packs.write_text("\n".join([f"pack {self.pack}", f"profiles {profiles}", *extra]) + "\n", encoding="utf-8")

    def run_installer(self, *extra: str, host: str = "cursor") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.checkout / "scripts" / "install-skills.py"), "--host", host,
             "--home", str(self.home), "--packs", str(self.packs), *extra],
            capture_output=True, text=True)

    @property
    def rules(self) -> Path:
        return self.home / "rules"

    def linked(self, name: str, src: Path) -> bool:
        return install.link_target(self.rules / name) == install.norm(src / name)

    def test_rules_link_file_by_file(self) -> None:
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIsNone(install.link_target(self.rules))
        self.assertTrue(self.linked("a.mdc", self.checkout / "rules"))
        self.assertTrue(self.linked("b.mdc", self.checkout / "rules"))
        self.assertTrue(self.linked("z.mdc", self.pack / "rules"))
        self.assertFalse(os.path.lexists(self.rules / "ops-only.mdc"))
        self.assertEqual((self.rules / "z.mdc").read_text(encoding="utf-8"),
                         (self.pack / "rules" / "z.mdc").read_text(encoding="utf-8"))
        self.assertRegex(result.stdout, r"--- Rules \(cursor\) ---\n(.*\n)*z\.mdc\s+rule-pack\s+-> ")
        self.assertEqual(self.run_installer().stdout.count("Linked rule"), 0)

    def test_rules_junction_is_retired_without_touching_sources(self) -> None:
        self.home.mkdir()
        install.make_link(self.rules, self.checkout / "rules")
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIsNone(install.link_target(self.rules))
        self.assertTrue(self.linked("a.mdc", self.checkout / "rules"))
        self.assertTrue(self.linked("z.mdc", self.pack / "rules"))
        self.assertEqual(sorted(p.name for p in (self.checkout / "rules").iterdir()), ["a.mdc", "b.mdc"])

        with self.subTest(junction="elsewhere"):
            self.setUp()
            self.home.mkdir()
            other = self.tmp / "other-rules"
            other.mkdir()
            install.make_link(self.rules, other)
            result = self.run_installer()
            self.assertEqual(result.returncode, 1)
            self.assertRegex(result.stdout, r"a\.mdc\s+agent-loop\s+SKIPPED: .* links to ")
            self.assertEqual(install.link_target(self.rules), install.norm(other))
            self.assertEqual(list(other.iterdir()), [])

        with self.subTest(junction="no file links"):
            self.setUp()
            self.home.mkdir()
            install.make_link(self.rules, self.checkout / "rules")
            copy = load_copy(self.checkout / "scripts" / "install-skills.py")
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(copy.os, "symlink", side_effect=OSError("simulated")), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = copy.main(["--host", "cursor", "--home", str(self.home), "--packs", str(self.packs)])
            self.assertEqual(code, 1)
            self.assertRegex(out.getvalue(), r"a\.mdc\s+agent-loop\s+SKIPPED: cannot create file links")
            self.assertEqual(install.link_target(self.rules), install.norm(self.checkout / "rules"))
            self.assertEqual(sorted(p.name for p in (self.checkout / "rules").iterdir()), ["a.mdc", "b.mdc"])

    def test_rule_name_has_one_owner(self) -> None:
        cases = ("plain file", "foreign link", "agent-loop name", "two packs")
        for case in cases:
            with self.subTest(case=case):
                self.setUp()
                self.rules.mkdir(parents=True)
                expected = {
                    "plain file": r"a\.mdc\s+agent-loop\s+SKIPPED: .* is a plain file",
                    "foreign link": r"z\.mdc\s+rule-pack\s+SKIPPED: .* outside the registered sources",
                    "agent-loop name": r"a\.mdc\s+rule-pack\s+SKIPPED: name also owned by agent-loop",
                    "two packs": r"z\.mdc\s+\S+\s+SKIPPED: name owned by more than one pack",
                }[case]
                if case == "plain file":
                    (self.rules / "a.mdc").write_text("mine", encoding="utf-8")
                elif case == "foreign link":
                    elsewhere = rule(self.tmp / "elsewhere" / "z.mdc")
                    install.make_link(self.rules / "z.mdc", elsewhere)
                elif case == "agent-loop name":
                    rule(self.pack / "rules" / "a.mdc")
                    (self.pack / "pack.toml").write_text(
                        RULE_PACK_TOML.format(version=2) + '\n[[rules]]\npath = "rules/a.mdc"\n', encoding="utf-8")
                else:
                    second = self.tmp / "second"
                    rule(second / "rules" / "z.mdc")
                    (second / "pack.toml").write_text('version = 2\nname = "second"\n\n[[rules]]\npath = "rules/z.mdc"\n',
                                                      encoding="utf-8")
                    self.write_packs("", f"pack {second}")
                result = self.run_installer()
                self.assertEqual(result.returncode, 1)
                self.assertRegex(result.stdout, expected)
                self.assertTrue(self.linked("b.mdc", self.checkout / "rules"))
                if case == "plain file":
                    self.assertEqual((self.rules / "a.mdc").read_text(encoding="utf-8"), "mine")
                if case == "foreign link":
                    self.assertEqual(install.link_target(self.rules / "z.mdc"), install.norm(elsewhere))
                if case == "two packs":
                    self.assertFalse(os.path.lexists(self.rules / "z.mdc"))

    def test_own_rule_replaces_foreign_link(self) -> None:
        self.rules.mkdir(parents=True)
        elsewhere = rule(self.tmp / "moved-checkout" / "rules" / "a.mdc")
        install.make_link(self.rules / "a.mdc", elsewhere)
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Linked rule: a.mdc", result.stdout)
        self.assertTrue(self.linked("a.mdc", self.checkout / "rules"))
        self.assertEqual((self.rules / "a.mdc").read_bytes(), (self.checkout / "rules" / "a.mdc").read_bytes())
        self.assertTrue(elsewhere.is_file())

    def test_rules_need_pack_version_2(self) -> None:
        self.write_pack(version=1)
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertIn("[[rules]] needs pack.toml version 2", result.stderr)
        self.assertFalse(os.path.lexists(self.rules / "z.mdc"))
        self.write_pack(version=2)
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.linked("z.mdc", self.pack / "rules"))

    def test_dsh_agents_from_selected_always_apply_rules(self) -> None:
        self.home.mkdir()
        agents = self.home / "AGENTS.md"
        agents.write_text("my notes", encoding="utf-8")
        result = self.run_installer(host="dsh")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        backups = list(self.home.glob("AGENTS.md.backup-*"))
        self.assertEqual([b.read_text(encoding="utf-8") for b in backups], ["my notes"])
        expected = f"{install.AGENTS_MARKER}\n\nA\n\nZ\n"
        self.assertEqual(agents.read_bytes().decode("utf-8"), expected)
        self.assertFalse((self.home / "rules").exists())

        (self.pack / "rules" / "z.mdc").unlink()
        (self.pack / "rules" / "z.mdc").mkdir()
        result = self.run_installer(host="dsh")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(agents.read_bytes().decode("utf-8"), expected)
        self.assertEqual(len(list(self.home.glob("AGENTS.md.backup-*"))), 1)

    def test_rule_links_follow_selection_and_uninstall(self) -> None:
        self.write_packs("ops")
        self.assertEqual(self.run_installer().returncode, 0)
        self.assertTrue(self.linked("ops-only.mdc", self.pack / "rules"))
        self.write_packs("")
        self.assertEqual(self.run_installer().returncode, 0)
        self.assertFalse(os.path.lexists(self.rules / "ops-only.mdc"))
        (self.rules / "mine.mdc").write_text("keep", encoding="utf-8")
        result = self.run_installer("--uninstall")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(sorted(p.name for p in self.rules.iterdir()), ["mine.mdc"])


def load_copy(path: Path):
    spec = importlib.util.spec_from_file_location("install_skills_rules_copy", path)
    module = sys.modules["install_skills_rules_copy"] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
