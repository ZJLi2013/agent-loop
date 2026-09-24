from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


SUBJECT_PREFIX = re.compile(
    r"^\[agent\s+(?P<task_id>[A-Za-z0-9._-]+)\]\s*(?P<title>.*)$",
    re.IGNORECASE,
)

_DO = re.compile(r"^DO\s+(?P<text>.+)$", re.IGNORECASE)


class Verb(Enum):
    OK = "OK"
    NO = "NO"
    STOP = "STOP"
    DO = "DO"


@dataclass(frozen=True)
class Page:
    task_id: str
    title: str
    body: str = ""

    @property
    def subject(self) -> str:
        return f"[agent {self.task_id}] {self.title}".rstrip()


@dataclass(frozen=True)
class Command:
    verb: Verb
    task_id: str
    text: str = ""


def render_page(task_id: str, title: str, body: str = "") -> Page:
    if not task_id or not re.fullmatch(r"[A-Za-z0-9._-]+", task_id):
        raise ValueError(f"invalid task_id: {task_id!r}")
    return Page(task_id=task_id, title=title.strip(), body=body.strip())


def parse_subject(subject: str) -> tuple[str, str] | None:
    s = re.sub(r"^(Re:\s*)+", "", (subject or "").strip(), flags=re.IGNORECASE)
    m = SUBJECT_PREFIX.match(s)
    if not m:
        return None
    return m.group("task_id"), m.group("title").strip()


def _command_line(body: str) -> str | None:
    for raw in (body or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">") or (
            line.startswith("On ") and line.endswith("wrote:")
        ):
            return None
        if line.startswith("-----Original Message-----"):
            return None
        return line
    return None


def parse_reply(body: str, *, task_id: str) -> Command | None:
    if not task_id:
        return None
    line = _command_line(body)
    if not line:
        return None
    token = line.split()[0].upper()
    if token in {Verb.OK.value, Verb.NO.value, Verb.STOP.value}:
        if len(line.split()) != 1:
            return None
        return Command(verb=Verb[token], task_id=task_id)
    m = _DO.match(line)
    if not m:
        return None
    text = m.group("text").strip()
    if not text:
        return None
    return Command(verb=Verb.DO, task_id=task_id, text=text)
