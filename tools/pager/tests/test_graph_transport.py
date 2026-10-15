import json


from pager.graph_transport import GraphTransport
from pager.protocol import Verb, render_page


class FakeGraphClient:
    def __init__(self, messages=None):
        self.messages = messages or []
        self.posts = []
        self.last_get = None

    def get(self, path, params=None):
        self.last_get = (path, params)
        return {"value": self.messages}

    def post(self, path, body):
        self.posts.append((path, body))
        return {"status": "ok"}


def message(
    message_id,
    subject,
    *,
    sender="owner@example.com",
    conversation_id="conv-1",
    preview="",
):
    return {
        "id": message_id,
        "subject": subject,
        "from": {"emailAddress": {"address": sender}},
        "conversationId": conversation_id,
        "bodyPreview": preview,
    }


def test_send_pages_control_address_and_tracks_task():
    client = FakeGraphClient()
    transport = GraphTransport(client, "owner@example.com")

    page_id = transport.send(render_page("T12", "批准 pipeline", "OK / NO"))

    assert page_id == "T12"
    path, payload = client.posts[0]
    assert path == "/me/sendMail"
    assert payload["message"]["subject"] == "[agent T12] 批准 pipeline"
    assert payload["message"]["toRecipients"][0]["emailAddress"]["address"] == (
        "owner@example.com"
    )


def test_poll_accepts_controller_reply_in_original_conversation_once():
    client = FakeGraphClient(
        [
            message(
                "reply-1",
                "Re: [agent T12] 批准 pipeline",
                preview="OK\r\n\r\nOutlook signature",
            ),
            message("original-1", "[agent T12] 批准 pipeline"),
        ]
    )
    transport = GraphTransport(client, "owner@example.com")
    transport.send(render_page("T12", "批准 pipeline"))

    commands = transport.poll()

    assert [(command.verb, command.task_id) for command in commands] == [
        (Verb.OK, "T12")
    ]
    assert transport.poll() == []


def test_poll_drops_wrong_sender():
    client = FakeGraphClient(
        [
            message(
                "reply-1",
                "Re: [agent T12] 批准 pipeline",
                sender="stranger@example.com",
                preview="OK",
            ),
            message("original-1", "[agent T12] 批准 pipeline"),
        ]
    )
    transport = GraphTransport(client, "owner@example.com")
    transport.send(render_page("T12", "批准 pipeline"))

    assert transport.poll() == []


def test_processed_reply_is_not_replayed_after_restart(tmp_path):
    state_path = tmp_path / "pager-state.json"
    client = FakeGraphClient(
        [
            message(
                "reply-1",
                "Re: [agent T12] 批准 pipeline",
                preview="OK",
            ),
            message("original-1", "[agent T12] 批准 pipeline"),
        ]
    )
    transport = GraphTransport(
        client, "owner@example.com", state_path=state_path
    )
    transport.send(render_page("T12", "批准 pipeline"))
    assert transport.poll()[0].verb is Verb.OK

    restarted = GraphTransport(
        client, "owner@example.com", state_path=state_path
    )

    assert restarted.poll() == []
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["seen"] == ["original-1", "reply-1"]
    assert not state_path.with_suffix(".json.tmp").exists()
