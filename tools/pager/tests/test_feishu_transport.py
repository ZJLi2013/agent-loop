
import pytest

from pager.feishu_transport import FeishuMessage, FeishuTransport
from pager.protocol import Verb, render_page


class FakeFeishuClient:
    def __init__(self):
        self.sent = []
        self.callback = None

    def send_text(self, chat_id, text):
        self.sent.append((chat_id, text))

    def start(self, callback):
        self.callback = callback


def transport(client=None, state_path=None):
    return FeishuTransport(
        client or FakeFeishuClient(),
        control_chat_id="chat-1",
        allowed_sender_ids={"user-1"},
        state_path=state_path,
    )


def message(text, *, message_id="message-1", chat_id="chat-1", sender="user-1"):
    return FeishuMessage(message_id, chat_id, sender, text)


def test_send_tracks_one_pending_task():
    client = FakeFeishuClient()
    channel = transport(client)

    page_id = channel.send(render_page("T12", "批准 pipeline", "OK / NO"))

    assert page_id == "T12"
    assert client.sent == [
        ("chat-1", "[agent T12] 批准 pipeline\n\nOK / NO")
    ]
    with pytest.raises(RuntimeError, match="pending task T12"):
        channel.send(render_page("T13", "另一项"))


@pytest.mark.parametrize(
    ("text", "verb", "command_text"),
    [
        ("OK", Verb.OK, ""),
        ("DO topN=5", Verb.DO, "topN=5"),
        ("先只生成摘要，全文暂缓", Verb.DO, "先只生成摘要，全文暂缓"),
    ],
)
def test_poll_accepts_explicit_and_natural_commands(text, verb, command_text):
    channel = transport()
    channel.send(render_page("T12", "批准 pipeline"))
    channel._inbox.put(message(text))

    commands = channel.poll()

    assert [(item.verb, item.task_id, item.text) for item in commands] == [
        (verb, "T12", command_text)
    ]
    assert channel.poll() == []


def test_poll_drops_wrong_chat_and_sender():
    channel = transport()
    channel.send(render_page("T12", "批准 pipeline"))
    channel._inbox.put(message("OK", message_id="wrong-chat", chat_id="chat-2"))
    channel._inbox.put(message("OK", message_id="wrong-user", sender="user-2"))

    assert channel.poll() == []
    assert channel._pending == "T12"
