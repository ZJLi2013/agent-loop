import pytest

from pager.protocol import Command, Verb
from pager.runner import PollError, listen


class SequenceTransport:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.polls = 0

    def send(self, page):
        raise NotImplementedError

    def poll(self):
        self.polls += 1
        outcome = next(self.outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class Clock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_listener_keeps_polling_after_three_empty_cycles():
    command = Command(Verb.DO, "T12", "inspect metrics")
    transport = SequenceTransport([[], [], [], [command]])
    sleeps = []

    commands = listen(transport, interval=2, sleep=sleeps.append)

    assert commands == [command]
    assert transport.polls == 4
    assert sleeps == [2, 2, 2]


def test_listener_retries_errors_with_bounded_backoff():
    command = Command(Verb.OK, "T12")
    transport = SequenceTransport(
        [RuntimeError("one"), RuntimeError("two"), [command]]
    )
    sleeps = []
    errors = []

    commands = listen(
        transport,
        max_errors=3,
        retry_base=2,
        max_backoff=3,
        sleep=sleeps.append,
        on_error=lambda error, count, delay: errors.append(
            (str(error), count, delay)
        ),
    )

    assert commands == [command]
    assert sleeps == [2, 3]
    assert errors == [("one", 1, 2), ("two", 2, 3)]


def test_listener_exits_after_error_limit():
    transport = SequenceTransport(
        [RuntimeError("one"), RuntimeError("two"), SystemExit(1)]
    )
    sleeps = []

    with pytest.raises(PollError, match="3 consecutive"):
        listen(
            transport,
            max_errors=3,
            retry_base=1,
            sleep=sleeps.append,
        )

    assert transport.polls == 3
    assert sleeps == [1, 2]
