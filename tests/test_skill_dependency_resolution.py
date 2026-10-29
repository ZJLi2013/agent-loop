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


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = sys.modules[name] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


install = load(SCRIPT, "install_skills")


def skill(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(f"---\nname: {path.name}\ndescription: d\n---\n", encoding="utf-8")
    return path


class DependencyResolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.checkout = self.tmp / "agent-loop"
        (self.checkout / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, self.checkout / "scripts")
        skill(self.checkout / "skills" / "work-planning")
        self.home = self.tmp / "home"
        self.packs = self.tmp / "packs.txt"

    def write(self, packs: dict[str, list[tuple[str, list[str], list[str]]]], profiles: str = "on") -> None:
        lines = []
        for pack, entries in packs.items():
            root = self.tmp / pack
            root.mkdir(exist_ok=True)
            body = f'version = 1\nname = "{pack}"\n'
            for name, requires, wanted in entries:
                if not (root / "skills" / name).exists():
                    skill(root / "skills" / name)
                body += f'\n[[skills]]\npath = "skills/{name}"\nrequires = {requires!r}\nprofiles = {wanted!r}\n'
            (root / "pack.toml").write_text(body.replace("'", '"'), encoding="utf-8")
            lines.append(f"pack {root}")
        self.packs.write_text("\n".join([*lines, f"profiles {profiles}"]) + "\n", encoding="utf-8")

    def run_installer(self, host: str = "cursor") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.checkout / "scripts" / "install-skills.py"), "--host", host,
             "--home", str(self.home), "--packs", str(self.packs)],
            capture_output=True, text=True)

    def dest(self) -> Path:
        return self.home / "skills"

    def linked(self, name: str, pack: str) -> bool:
        return install.link_target(self.dest() / name) == install.norm(self.tmp / pack / "skills" / name)

    def test_requires_resolves_to_a_skill_of_another_pack(self) -> None:
        self.write({"a": [("consumer", ["provider"], [])], "b": [("provider", [], ["on"])]})
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.linked("consumer", "a"))
        self.assertTrue(self.linked("provider", "b"))

    def test_a_broken_closure_skips_every_dependent_and_keeps_independent_skills(self) -> None:
        cases = {
            "unselected": ({"b": [("provider", ["leaf"], []), ("leaf", [], ["off"])]}, None),
            "missing": ({"b": [("provider", ["leaf"], [])]}, None),
            "two owners": ({"b": [("provider", ["leaf"], []), ("leaf", [], [])], "c": [("leaf", [], [])]}, None),
            "plain directory": ({"b": [("provider", ["leaf"], []), ("leaf", [], [])]}, "leaf"),
        }
        for case, (packs, plain) in cases.items():
            with self.subTest(case=case):
                self.setUp()
                self.write({"a": [("consumer", ["provider"], []), ("alone", [], [])], **packs})
                if plain:
                    (self.dest() / plain).mkdir(parents=True)
                    (self.dest() / plain / "mine.md").write_text("keep", encoding="utf-8")
                result = self.run_installer()
                self.assertEqual(result.returncode, 1)
                for name in ("consumer", "provider"):
                    self.assertRegex(result.stdout, rf"{name}\s+\w+\s+SKIPPED: requires ")
                    self.assertFalse(os.path.lexists(self.dest() / name))
                self.assertTrue(self.linked("alone", "a"))
                if plain:
                    self.assertEqual((self.dest() / plain / "mine.md").read_text(encoding="utf-8"), "keep")

    def test_a_cycle_and_its_dependents_are_skipped(self) -> None:
        self.write({"a": [("x", ["y"], []), ("y", ["x"], []), ("consumer", ["x"], []), ("alone", [], [])]})
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.count("SKIPPED: requires cycle"), 2)
        self.assertRegex(result.stdout, r"consumer\s+a\s+SKIPPED: requires x, which is not installable")
        for name in ("x", "y", "consumer"):
            self.assertFalse(os.path.lexists(self.dest() / name))
        self.assertTrue(self.linked("alone", "a"))

    def test_a_skill_moved_out_of_agent_loop_switches_over_in_one_run(self) -> None:
        for host in ("cursor", "dsh"):
            with self.subTest(host=host):
                self.setUp()
                old = skill(self.checkout / "skills" / "provider")
                own_dest = self.home / ("skills-cursor" if host == "cursor" else "skills")
                own_dest.mkdir(parents=True)
                install.make_link(own_dest / "provider", old)
                shutil.rmtree(old)
                self.write({"a": [("consumer", ["provider"], [])], "b": [("provider", [], [])]})
                result = self.run_installer(host)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(self.linked("provider", "b"))
                self.assertTrue(self.linked("consumer", "a"))
                if host == "cursor":
                    self.assertFalse(os.path.lexists(own_dest / "provider"))
                again = self.run_installer(host)
                self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
                self.assertEqual(again.stdout.count("Linked skill"), 0)

    def test_a_provider_that_fails_to_link_skips_its_dependents(self) -> None:
        self.write({"a": [("consumer", ["provider"], []), ("alone", [], [])], "b": [("provider", [], [])]})
        copy = load(self.checkout / "scripts" / "install-skills.py", "install_skills_copy")
        real = copy.make_link

        def make_link(link: Path, target: Path) -> None:
            if link.name == "provider":
                raise OSError("simulated")
            real(link, target)

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(copy, "make_link", make_link), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = copy.main(["--host", "cursor", "--home", str(self.home), "--packs", str(self.packs)])
        self.assertEqual(code, 1)
        self.assertRegex(out.getvalue(), r"provider\s+b\s+SKIPPED: cannot link .*simulated")
        self.assertRegex(out.getvalue(), r"consumer\s+a\s+SKIPPED: requires provider, which was not linked")
        self.assertNotIn("Linked skill: consumer", out.getvalue())
        self.assertTrue(self.linked("alone", "a"))

    def test_a_rejected_provider_keeps_the_old_links_of_its_dependents(self) -> None:
        faults = {
            "none": None,
            "make_link": r"cannot link .*simulated",
            "remove_link": r"cannot link .*simulated",
            "target conflict": r".*skills-cursor.provider already exists",
        }
        for location in ("old pack", "moved out of agent-loop"):
            for fault, reason in faults.items():
                with self.subTest(old_links=location, fault=fault):
                    self.setUp()
                    if location == "old pack":
                        old, links = self.tmp / "old", self.dest()
                    else:
                        old, links = self.checkout, self.home / "skills-cursor"
                    self.write({"old": [], "a": [("consumer", ["provider"], []), ("downstream", ["consumer"], []),
                                                  ("alone", [], [])], "b": [("provider", [], [])]})
                    links.mkdir(parents=True)
                    for name in ("consumer", "downstream", "provider"):
                        install.make_link(links / name, skill(old / "skills" / name))
                        if old == self.checkout:
                            shutil.rmtree(old / "skills" / name)
                    if fault == "target conflict":
                        builtin = self.home / "skills-cursor" / "provider"
                        if os.path.lexists(builtin):
                            install.remove_link(builtin)
                        builtin.mkdir(parents=True)
                    copy = load(self.checkout / "scripts" / "install-skills.py", "install_skills_copy")
                    real = getattr(copy, fault, None)

                    def failing(link: Path, *rest: Path) -> None:
                        if link.name == "provider":
                            raise OSError("simulated")
                        real(link, *rest)

                    def run() -> tuple[int, str]:
                        out = io.StringIO()
                        with contextlib.ExitStack() as stack:
                            if real:
                                stack.enter_context(mock.patch.object(copy, fault, failing))
                            stack.enter_context(contextlib.redirect_stdout(out))
                            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
                            code = copy.main(["--host", "cursor", "--home", str(self.home), "--packs", str(self.packs)])
                        return code, out.getvalue()

                    code, out = run()
                    self.assertTrue(self.linked("alone", "a"))
                    if reason is None:
                        self.assertEqual(code, 0, out)
                        for name, pack in (("consumer", "a"), ("downstream", "a"), ("provider", "b")):
                            self.assertTrue(self.linked(name, pack))
                            if links != self.dest():
                                self.assertFalse(os.path.lexists(links / name))
                        again, rerun = run()
                        self.assertEqual(again, 0, rerun)
                        self.assertNotIn("Linked skill", rerun)
                        continue
                    self.assertEqual(code, 1)
                    self.assertRegex(out, rf"provider\s+b\s+SKIPPED: {reason}")
                    for name, provider in (("consumer", "provider"), ("downstream", "consumer")):
                        self.assertRegex(out, rf"{name}\s+a\s+SKIPPED: requires {provider}, ")
                        self.assertNotIn(f"Linked skill: {name}", out)
                        self.assertEqual(install.link_target(links / name), install.norm(old / "skills" / name))
                        if links != self.dest():
                            self.assertFalse(os.path.lexists(self.dest() / name))

    def test_installs_without_dependencies_are_unchanged(self) -> None:
        own_dest = self.home / "skills-cursor"
        own_dest.mkdir(parents=True)
        install.make_link(own_dest / "work-planning", skill(self.tmp / "moved-checkout" / "work-planning"))
        self.packs = self.tmp / "absent.txt"
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(install.link_target(own_dest / "work-planning"),
                         install.norm(self.checkout / "skills" / "work-planning"))
        self.packs = self.tmp / "packs.txt"
        self.write({"a": [("alone", [], [])]})
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.linked("alone", "a"))


if __name__ == "__main__":
    unittest.main()
