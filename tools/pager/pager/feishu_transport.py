from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, SimpleQueue
from typing import Callable, Protocol

from pager.protocol import Command, Page, Verb, parse_reply


@dataclass(frozen=True)
class FeishuMessage:
    message_id: str
    chat_id: str
    sender_id: str
    text: str


class FeishuClient(Protocol):
    def send_text(self, chat_id: str, text: str) -> None: ...

    def start(self, callback: Callable[[FeishuMessage], None]) -> None: ...


class LarkFeishuClient:
    def __init__(self, app_id: str, app_secret: str) -> None:
        try:
            import lark_oapi as lark
            from lark_oapi.api.im.v1 import (
                CreateMessageRequest,
                CreateMessageRequestBody,
            )
        except ImportError as exc:
            raise RuntimeError(
                'Feishu transport requires: pip install "pager[feishu]"'
            ) from exc

        self._lark = lark
        self._create_request = CreateMessageRequest
        self._create_body = CreateMessageRequestBody
        self._app_id = app_id
        self._app_secret = app_secret
        self._api = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .build()
        )

    def send_text(self, chat_id: str, text: str) -> None:
        body = (
            self._create_body.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content(json.dumps({"text": text}, ensure_ascii=False))
            .build()
        )
        request = (
            self._create_request.builder()
            .receive_id_type("chat_id")
            .request_body(body)
            .build()
        )
        response = self._api.im.v1.message.create(request)
        if not response.success():
            raise RuntimeError(
                f"Feishu send failed: code={response.code}, msg={response.msg}"
            )

    def start(self, callback: Callable[[FeishuMessage], None]) -> None:
        handler = (
            self._lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(
                lambda data: _dispatch_event(data, callback)
            )
            .build()
        )
        client = self._lark.ws.Client(
            self._app_id,
            self._app_secret,
            event_handler=handler,
        )
        client.start()


@dataclass
class FeishuTransport:
    client: FeishuClient
    control_chat_id: str
    allowed_sender_ids: set[str]
    state_path: Path | None = None
    _pending: str | None = None
    _seen: set[str] = field(default_factory=set)
    _inbox: SimpleQueue[FeishuMessage] = field(default_factory=SimpleQueue)
    _started: bool = False
    _listener_error: BaseException | None = None
    _start_lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        if not self.control_chat_id:
            raise ValueError("control_chat_id is required")
        if not self.allowed_sender_ids:
            raise ValueError("allowed_sender_ids is required")
        if self.state_path is not None:
            self.state_path = Path(self.state_path)
            self._load_state()

    def send(self, page: Page) -> str:
        if self._pending is not None:
            raise RuntimeError(
                f"Feishu transport already has pending task {self._pending}"
            )
        text = page.subject
        if page.body:
            text += f"\n\n{page.body}"
        self.client.send_text(self.control_chat_id, text)
        self._pending = page.task_id
        self._save_state()
        return page.task_id

    def notify(self, title: str, body: str) -> None:
        text = f"[pager] {title}".rstrip()
        if body:
            text += f"\n\n{body}"
        self.client.send_text(self.control_chat_id, text)

    def poll(self) -> list[Command]:
        self._ensure_listener()
        if self._listener_error is not None:
            raise RuntimeError("Feishu listener stopped") from self._listener_error

        commands: list[Command] = []
        while True:
            try:
                message = self._inbox.get_nowait()
            except Empty:
                break
            if (
                message.message_id in self._seen
                or message.chat_id != self.control_chat_id
                or message.sender_id not in self.allowed_sender_ids
            ):
                continue
            self._seen.add(message.message_id)
            if self._pending is None:
                continue
            command = parse_reply(message.text, task_id=self._pending)
            if command is None and message.text.strip():
                command = Command(
                    verb=Verb.DO,
                    task_id=self._pending,
                    text=message.text.strip(),
                )
            if command is not None:
                commands.append(command)
                self._pending = None
        self._save_state()
        return commands

    def _ensure_listener(self) -> None:
        with self._start_lock:
            if self._started:
                return
            self._started = True
            thread = threading.Thread(target=self._listen, daemon=True)
            thread.start()

    def _listen(self) -> None:
        try:
            self.client.start(self._inbox.put)
        except BaseException as exc:
            self._listener_error = exc

    def _load_state(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            pending = state["pending"]
            if pending is not None and not isinstance(pending, str):
                raise TypeError
            self._pending = pending
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
            "pending": self._pending,
            "seen": sorted(self._seen),
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(state, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temp_path, self.state_path)


def from_env(control_chat_id: str, state_path: Path) -> FeishuTransport:
    app_id = os.getenv("PAGER_FEISHU_APP_ID", "")
    app_secret = os.getenv("PAGER_FEISHU_APP_SECRET", "")
    sender_ids = {
        value.strip()
        for value in os.getenv("PAGER_FEISHU_ALLOWED_SENDER_IDS", "").split(",")
        if value.strip()
    }
    if not app_id or not app_secret:
        raise SystemExit(
            "PAGER_FEISHU_APP_ID and PAGER_FEISHU_APP_SECRET are required"
        )
    if not sender_ids:
        raise SystemExit("PAGER_FEISHU_ALLOWED_SENDER_IDS is required")
    return FeishuTransport(
        LarkFeishuClient(app_id, app_secret),
        control_chat_id=control_chat_id,
        allowed_sender_ids=sender_ids,
        state_path=state_path,
    )


def _dispatch_event(
    data: object, callback: Callable[[FeishuMessage], None]
) -> None:
    event = getattr(data, "event", None)
    message = getattr(event, "message", None)
    sender = getattr(event, "sender", None)
    sender_id = getattr(sender, "sender_id", None)
    if getattr(message, "message_type", None) != "text":
        return
    try:
        content = json.loads(getattr(message, "content", ""))
    except (TypeError, ValueError):
        return
    text = content.get("text") if isinstance(content, dict) else None
    if not isinstance(text, str):
        return
    value = FeishuMessage(
        message_id=getattr(message, "message_id", "") or "",
        chat_id=getattr(message, "chat_id", "") or "",
        sender_id=getattr(sender_id, "open_id", "") or "",
        text=text,
    )
    if value.message_id and value.chat_id and value.sender_id:
        callback(value)
