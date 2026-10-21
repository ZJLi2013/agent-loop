#!/usr/bin/env python3
"""Refuse an issue title and body that carry material a public issue must not contain.

usage: check_report.py --title TITLE BODY_FILE
Exit 0 when clean; exit 1 and one line per hit otherwise.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("local path", re.compile(r"[A-Za-z]:\\Users\\|/mnt/[a-z]/|/home/[^/\s]+/")),
    # Mainland GPU models from rules/external-output-boundary.mdc.
    ("gpu model", re.compile(r"\bMI(?:308XHF|308X|308|258|108)\b")),
    ("credential", re.compile(
        r"\b(?:ghp_|gho_|github_pat_)\w{20,}|\bsk-[\w-]{20,}|\bAKIA[0-9A-Z]{16}\b"
        r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
        r"|\b(?:token|password|passwd|api_key|apikey|secret)\s*[=:]\s*\S+",
        re.IGNORECASE,
    )),
    ("transcript", re.compile(r"<user_query>|^\s*\[(?:user|assistant)\]|^\s*(?:Human|Assistant):", re.MULTILINE)),
]
HOST = re.compile(r"\b(?:[a-z0-9-]+\.){2,}[a-z][a-z0-9-]*\b", re.IGNORECASE)
PUBLIC_DOMAINS = ("github.com", "githubusercontent.com", "github.io", "arxiv.org", "python.org", "pypi.org",
                  "cursor.com", "openai.com", "anthropic.com", "readthedocs.io")
FILE_SUFFIXES = {"md", "mdc", "py", "pyc", "json", "jsonl", "ps1", "sh", "txt", "yml", "yaml", "toml", "log", "lock"}
AI_USE = re.compile(r"^\s*(?:#+\s*)?AI use\b", re.IGNORECASE | re.MULTILINE)


def _hosts(line: str) -> list[str]:
    hits = []
    for match in HOST.finditer(line):
        name = match.group(0).lower()
        if name.rsplit(".", 1)[-1] in FILE_SUFFIXES:
            continue
        if any(name == d or name.endswith("." + d) for d in PUBLIC_DOMAINS):
            continue
        hits.append(match.group(0))
    return hits


def check(title: str, body: str) -> list[str]:
    hits = []
    for where, text in (("title", title), ("body", body)):
        for number, line in enumerate(text.splitlines(), start=1):
            for category, pattern in PATTERNS:
                hits += [f"{where}:{number}: {category}: {m.group(0)}" for m in pattern.finditer(line)]
            hits += [f"{where}:{number}: host name: {name}" for name in _hosts(line)]
    if not AI_USE.search(body):
        hits.append("body: missing AI use section")
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--title", required=True)
    parser.add_argument("body", type=Path)
    args = parser.parse_args(argv)
    hits = check(args.title, args.body.read_text(encoding="utf-8"))
    for hit in hits:
        print(hit)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
