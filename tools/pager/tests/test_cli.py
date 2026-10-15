import json

from pager.cli import run
from pager.protocol import Command, Verb, render_page
from pager.transport import FakeTransport


class SequenceTransport:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.notifications = []

    def send(self, page):
        raise NotImplementedError

    def notify(self, title, body):
        self.notifications.append((title, body))

    def poll(self):
        outcome = next(self.outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def test_send_outputs_stable_json(capsys, tmp_path):
    transport = FakeTransport()
    captured = {}

    def factory(address, state_path):
        captured["address"] = address
        captured["state_path"] = state_path
        return transport

    result = run(
        [
            "send",
            "--address",
            "owner@example.com",
            "--state",
            str(tmp_path / "state.json"),
            "--task-id",
            "T12",
            "--title",
            "批准 pipeline",
            "--body",
            "OK / NO",
        ],
        transport_factory=factory,
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "sent",
        "task_id": "T12",
    }
    assert captured == {
        "address": "owner@example.com",
        "state_path": tmp_path / "state.json",
    }


def test_wait_outputs_command_json(capsys):
    transport = FakeTransport()
    page_id = transport.send(render_page("T12", "批准 pipeline"))
    transport.inject_reply(page_id, "DO topN=5")

    result = run(
        [
            "wait",
            "--address",
            "owner@example.com",
            "--timeout",
            "0",
        ],
        transport_factory=lambda address, state_path: transport,
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "command"
    assert payload["commands"] == [
        {"verb": Verb.DO.value, "task_id": "T12", "text": "topN=5"}
    ]


def test_serve_survives_empty_cycles_until_command(capsys):
    command_transport = SequenceTransport(
        [[], [], [], [Command(Verb.OK, "T12")]]
    )
    sleeps = []

    result = run(
        ["serve", "--address", "owner@example.com", "--interval", "2"],
        transport_factory=lambda address, state_path: command_transport,
        sleep=sleeps.append,
    )

    assert result == 0
    assert sleeps == [2, 2, 2]
    assert json.loads(capsys.readouterr().out)["commands"][0]["verb"] == "OK"
