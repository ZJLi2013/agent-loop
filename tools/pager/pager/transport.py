from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from pager.protocol import Command, Page, parse_reply, parse_subject


@dataclass(frozen=True)
class Envelope:
    message_id: str
    subject: str
    body: str
    in_reply_to: str | None = None


class Transport(Protocol):
    def send(self, page: Page) -> str: ...

    def notify(self, title: str, body: str) -> None: ...

    def poll(self) -> list[Command]: ...


@dataclass
class FakeTransport:
    """In-memory mailbox. Tests inject replies; production Graph is a later adapter."""

    _outbox: dict[str, Page] = field(default_factory=dict)
    _inbox: list[Envelope] = field(default_factory=list)
    _notifications: list[tuple[str, str]] = field(default_factory=list)
    _seen: set[str] = field(default_factory=set)
    _seq: int = 0

    def send(self, page: Page) -> str:
        self._seq += 1
        message_id = f"out-{self._seq}"
        self._outbox[message_id] = page
        return message_id

    def notify(self, title: str, body: str) -> None:
        self._notifications.append((title, body))

    def inject_reply(self, page_id: str, body: str) -> str:
        page = self._outbox[page_id]
        self._seq += 1
        reply_id = f"in-{self._seq}"
        self._inbox.append(
            Envelope(
                message_id=reply_id,
                subject=f"Re: {page.subject}",
                body=body,
                in_reply_to=page_id,
            )
        )
        return reply_id

    def poll(self) -> list[Command]:
        commands: list[Command] = []
        for env in self._inbox:
            if env.message_id in self._seen:
                continue
            self._seen.add(env.message_id)
            if env.in_reply_to not in self._outbox:
                continue
            page = self._outbox[env.in_reply_to]
            parsed = parse_subject(env.subject)
            if parsed and parsed[0] != page.task_id:
                continue
            cmd = parse_reply(env.body, task_id=page.task_id)
            if cmd is not None:
                commands.append(cmd)
        return commands
