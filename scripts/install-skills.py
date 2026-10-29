"""Link agent-loop's skills and the selected skills of registered packs into one host. Idempotent.

    python scripts/install-skills.py --host cursor|dsh [--home DIR] [--packs FILE] [--uninstall]

A skill pack is a directory with a pack.toml; ~/.agent-loop/packs.txt lists the packs, repository checkouts
and active profiles of this machine. Formats and the rules below are in docs/usage.md#skill-packs.
Exits 1 when any skill was skipped or any input could not be read.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
import graphlib
import os
from pathlib import Path
import subprocess
import sys
import tomllib

REPO = Path(__file__).resolve().parents[1]
OWN = "agent-loop"


@dataclass
class Skill:
    name: str
    src: Path
    owner: str
    dest: Path
    checkout: Path | None = None
    requires: list[str] = field(default_factory=list)
    selected: bool = True
    problem: str = ""
    own: bool = False  # set only when enumerating agent-loop's skills/, never from a pack's chosen name


def norm(path: str | Path) -> str:
    text = str(path)
    if text.startswith("\\\\?\\"):
        text = text[4:]
    # Resolve only the parent: 8.3 names and aliased directories compare equal, and a link is not followed to its target.
    head, tail = os.path.split(os.path.abspath(text))
    return os.path.normcase(os.path.join(os.path.realpath(head), tail))


def link_target(path: Path) -> str | None:
    try:
        return norm(os.readlink(path))
    except (OSError, ValueError):
        return None


def make_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        import _winapi  # junctions need no administrator rights, unlike directory symlinks

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def remove_link(link: Path) -> None:
    if os.name == "nt":
        os.rmdir(link)
    else:
        os.unlink(link)


def inside(target: str, roots: list[str]) -> bool:
    return any(target == root or target.startswith(root + os.sep) for root in roots)


def read_packs(path: Path, errors: list[str]) -> tuple[list[Path], dict[str, Path], set[str]]:
    packs: list[Path] = []
    repos: dict[str, Path] = {}
    profiles: set[str] = set()
    if not path.exists():
        return packs, repos, profiles
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, rest = line.partition(" ")
        rest = rest.strip()
        parts = rest.split(None, 1)
        if key == "pack" and rest:
            packs.append(Path(rest))
        elif key == "repo" and len(parts) == 2:
            repos[parts[0]] = Path(parts[1])
        elif key == "profiles":
            profiles = {p.strip() for p in rest.split(",") if p.strip()}
        else:
            errors.append(f"{path}:{number}: cannot read {raw.strip()!r}")
    return packs, repos, profiles


def read_pack(root: Path, repos: dict[str, Path], profiles: set[str], dest: Path,
              errors: list[str]) -> list[Skill]:
    try:
        data = tomllib.loads((root / "pack.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"pack {root}: {exc}")
        return []
    if data.get("version") != 1:
        errors.append(f"pack {root}: unsupported pack.toml version {data.get('version')!r}")
        return []
    name = data.get("name") or root.name
    skills = []
    for entry in data.get("skills", []):
        repo = entry.get("repo")
        if repo and repo not in repos:
            errors.append(f"pack {name}: repo {repo!r} is not registered in packs.txt")
            continue
        base = repos[repo] if repo else root
        src = base / entry.get("path", "")
        if not (src / "SKILL.md").is_file():
            errors.append(f"pack {name}: no SKILL.md at {src}")
            continue
        wanted = entry.get("profiles") or []
        skills.append(Skill(src.name, src, name, dest, base if repo else None,
                            list(entry.get("requires", [])), not wanted or bool(profiles & set(wanted))))
    return skills


def resolve_installable(skills: list[Skill]) -> list[Skill]:
    ok = {s.name: s for s in skills if not s.problem}
    while True:
        dropped = True
        while dropped:
            dropped = False
            for s in list(ok.values()):
                missing = [r for r in s.requires if r not in ok]
                if missing:
                    s.problem = "requires " + ", ".join(missing) + ", which is not installable"
                    del ok[s.name]
                    dropped = True
        try:
            order = graphlib.TopologicalSorter({n: s.requires for n, s in ok.items()}).static_order()
            return [ok[name] for name in order]
        except graphlib.CycleError as exc:
            cycle = exc.args[1]
            for name in set(cycle):
                ok.pop(name).problem = "requires cycle " + " -> ".join(cycle)


def git_state(skill: Skill) -> str:
    def git(*argv: str) -> str | None:
        result = subprocess.run(["git", "-C", str(skill.checkout), *argv], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None

    behind = git("rev-list", "--count", "HEAD..@{u}") or "?"
    dirty = git("status", "--porcelain", "--", str(skill.src))
    return f"   behind={behind} dirty={'?' if dirty is None else 'yes' if dirty else 'no'}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", choices=("cursor", "dsh"), required=True)
    parser.add_argument("--home", type=Path, help="host home (default ~/.cursor, or DSH_HOME for dsh)")
    parser.add_argument("--packs", type=Path, default=Path.home() / ".agent-loop" / "packs.txt")
    parser.add_argument("--uninstall", action="store_true", help="remove the links whose target is a registered source")
    args = parser.parse_args(argv)
    if args.host == "cursor":
        home = args.home or Path.home() / ".cursor"
        own_dest, pack_dest = home / "skills-cursor", home / "skills"
    else:
        home = args.home or (Path(os.environ["DSH_HOME"]) if os.environ.get("DSH_HOME") else None)
        if home is None:
            parser.error("dsh home not set: pass --home <path> or set DSH_HOME (dsh defaults to ~/.dsh)")
        own_dest = pack_dest = home / "skills"
    dests = list(dict.fromkeys([own_dest, pack_dest]))

    errors: list[str] = []
    own = [Skill(d.name, d, OWN, own_dest, own=True) for d in sorted((REPO / "skills").iterdir()) if (d / "SKILL.md").is_file()]
    pack_roots, repos, profiles = read_packs(args.packs, errors)
    packed = [s for root in pack_roots for s in read_pack(root, repos, profiles, pack_dest, errors)]
    roots = [norm(REPO / "skills"), *(norm(r) for r in pack_roots), *(norm(r) for r in repos.values())]

    if args.uninstall:
        for dest in dests:
            for entry in sorted(dest.iterdir()) if dest.is_dir() else []:
                target = link_target(entry)
                if target and inside(target, roots):
                    remove_link(entry)
                    print(f"Removed skill: {entry.name}")
        return 0

    own_names = {s.name for s in own}
    chosen = [s for s in packed if s.selected]
    counts = Counter(s.name for s in chosen)
    for s in chosen:
        builtin = own_dest / s.name
        if s.name in own_names:
            s.problem = "name also owned by agent-loop"
        elif counts[s.name] > 1:
            s.problem = "name owned by more than one pack: " + ", ".join(sorted(o.owner for o in chosen if o.name == s.name))
        elif own_dest != pack_dest and os.path.lexists(builtin) and not inside(link_target(builtin) or "", roots):
            s.problem = f"{builtin} already exists"
    install = resolve_installable(own + chosen)
    desired = {norm(s.dest / s.name): norm(s.src) for s in install}
    names = {s.name for s in own + chosen}

    for dest in dests:
        dest.mkdir(parents=True, exist_ok=True)
        for entry in sorted(dest.iterdir()):
            target = link_target(entry)
            if target and inside(target, roots) and entry.name not in names:
                try:
                    remove_link(entry)
                except OSError as exc:
                    errors.append(f"cannot remove {entry}: {exc}")
                    continue
                print(f"Removed link: {entry.name}")

    failed = {s.name for s in own + packed if s.problem}
    for s in install:
        link = s.dest / s.name
        target = link_target(link)
        current = target == norm(s.src)
        # On Cursor a skill moved between agent-loop and a pack leaves its old link in the other directory.
        stale = [d / s.name for d in dests if d != s.dest and inside(link_target(d / s.name) or "", roots)]
        blocked = [r for r in s.requires if r in failed]
        if blocked:
            s.problem = "requires " + ", ".join(blocked) + ", which was not linked"
        elif current and not stale:
            continue
        elif target is not None and not s.own and not inside(target, roots):
            s.problem = f"{link} links to {target}, outside the registered sources"
        elif target is None and os.path.lexists(link):
            s.problem = f"{link} is a plain directory"
        else:
            try:
                for old in stale:
                    remove_link(old)
                    print(f"Removed link: {old.name}")
                if not current:
                    if target is not None:
                        remove_link(link)  # an old registered source, or an agent-loop skill left behind by a moved checkout
                    make_link(link, s.src)
            except OSError as exc:
                s.problem = f"cannot link {link}: {exc}"
        if s.problem:
            failed.add(s.name)
        elif not current:
            print(f"Linked skill: {s.name}")

    width = max(len(owner) for owner in ["unmanaged", OWN, *(s.owner for s in packed)])
    print(f"\n--- Skills ({args.host}) ---")
    for s in own + packed:
        if s.problem:
            status = f"SKIPPED: {s.problem}"
        elif not s.selected:
            status = "not selected by profiles"
        else:
            status = f"-> {s.src}" + (git_state(s) if s.checkout else "")
        print(f"{s.name:<26} {s.owner:<{width}} {status}")
    for dest in dests:
        for entry in sorted(dest.iterdir()):
            target = link_target(entry)
            if target and norm(entry) not in desired:
                print(f"{entry.name:<26} {'unmanaged':<{width}} -> {target}")
    problems = errors + [f"{s.name}: {s.problem}" for s in own + packed if s.problem]
    for problem in problems:
        print(f"ERROR: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
