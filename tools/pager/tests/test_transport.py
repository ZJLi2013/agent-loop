from pager.protocol import Verb, render_page
from pager.transport import Envelope, FakeTransport


def test_fake_roundtrip_ok():
    box = FakeTransport()
    page_id = box.send(render_page("T12", "批准 pipeline"))
    box.inject_reply(page_id, "OK\n\n> quoted original\n")
    cmds = box.poll()
    assert len(cmds) == 1
    assert cmds[0].verb is Verb.OK
    assert cmds[0].task_id == "T12"
    assert box.poll() == []


def test_reply_without_in_reply_to_dropped():
    box = FakeTransport()
    box.send(render_page("T12", "批准 pipeline"))
    box._inbox.append(
        Envelope(message_id="spam", subject="Re: [agent T12] 批准 pipeline", body="OK")
    )
    assert box.poll() == []


def test_reply_to_unknown_page_dropped():
    box = FakeTransport()
    box.send(render_page("T12", "批准 pipeline"))
    box._inbox.append(
        Envelope(
            message_id="orphan",
            subject="Re: [agent T12] 批准 pipeline",
            body="OK",
            in_reply_to="out-999",
        )
    )
    assert box.poll() == []
