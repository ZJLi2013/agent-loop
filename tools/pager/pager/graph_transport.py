from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pager.protocol import Command, Page, parse_reply, parse_subject


class GraphClient(Protocol):
    def get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...

    def post(self, path: str, body: dict[str, Any]) -> Any: ...


@dataclass
class GraphTransport:
    client: GraphClient
    control_address: str
    poll_limit: int = 50
    state_path: Path | None = None
    _pending: set[str] = field(default_factory=set)
    _conversations: dict[str, set[str]] = field(default_factory=dict)
    _seen: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.state_path is not None:
            self.state_path = Path(self.state_path)
            self._load_state()

    def send(self, page: Page) -> str:
        self._post_message(page.subject, page.body, importance="high")
        self._pending.add(page.task_id)
        self._save_state()
        return page.task_id

    def notify(self, title: str, body: str) -> None:
        self._post_message(f"[pager] {title}".rstrip(), body)

    def _post_message(
        self, subject: str, body: str, *, importance: str = "normal"
    ) -> None:
        message = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [
                {"emailAddress": {"address": self.control_address}}
            ],
            "importance": importance,
        }
        self.client.post("/me/sendMail", {"message": message})

    def poll(self) -> list[Command]:
        data = self.client.get(
            "/me/mailFolders/inbox/messages",
            params={
                "$top": str(self.poll_limit),
                "$orderby": "receivedDateTime desc",
                "$select": (
                    "id,subject,from,receivedDateTime,bodyPreview,conversationId"
                ),
            },
        )
        messages = data.get("value", [])
        self._learn_conversations(messages)

        commands: list[Command] = []
        for message in messages:
            message_id = message.get("id", "")
            if not message_id or message_id in self._seen:
                continue
            self._seen.add(message_id)

            subject = message.get("subject", "")
            parsed = parse_subject(subject)
            if parsed is None or not _is_reply(subject):
                continue
            task_id, _ = parsed
            if task_id not in self._pending or not self._from_controller(message):
                continue
            conversation_id = message.get("conversationId", "")
            if conversation_id not in self._conversations.get(task_id, set()):
                continue
            command = parse_reply(
                message.get("bodyPreview", ""), task_id=task_id
            )
            if command is not None:
                commands.append(command)
                self._pending.discard(task_id)
                self._conversations.pop(task_id, None)
        self._save_state()
        return commands

    def _learn_conversations(self, messages: list[dict[str, Any]]) -> None:
        for message in messages:
            subject = message.get("subject", "")
            parsed = parse_subject(subject)
            if parsed is None or _is_reply(subject):
                continue
            task_id, _ = parsed
            conversation_id = message.get("conversationId", "")
            if (
                task_id in self._pending
                and conversation_id
                and self._from_controller(message)
            ):
                self._conversations.setdefault(task_id, set()).add(
                    conversation_id
                )

    def _from_controller(self, message: dict[str, Any]) -> bool:
        sender = (
            message.get("from", {})
            .get("emailAddress", {})
            .get("address", "")
        )
        return sender.casefold() == self.control_address.casefold()

    def _load_state(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self._pending = set(state["pending"])
            self._conversations = {
                task_id: set(conversation_ids)
                for task_id, conversation_ids in state["conversations"].items()
            }
            self._seen = set(state["seen"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError(
                f"invalid pager state: {self.state_path}"
            ) from exc

    def _save_state(self) -> None:
        if self.state_path is None:
            return
        state = {
            "version": 1,
            "pending": sorted(self._pending),
            "conversations": {
                task_id: sorted(conversation_ids)
                for task_id, conversation_ids in sorted(
                    self._conversations.items()
                )
            },
            "seen": sorted(self._seen),
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(state, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temp_path, self.state_path)


def _is_reply(subject: str) -> bool:
    return subject.lstrip().casefold().startswith("re:")
