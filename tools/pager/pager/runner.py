from __future__ import annotations

import time
from collections.abc import Callable

from pager.protocol import Command
from pager.transport import Transport


class PollError(RuntimeError):
    pass


def listen(
    transport: Transport,
    *,
    interval: float = 10,
    max_errors: int = 3,
    retry_base: float = 5,
    max_backoff: float = 300,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    heartbeat_interval: float | None = None,
    heartbeat: Callable[[], None] | None = None,
    on_error: Callable[[BaseException, int, float | None], None] | None = None,
    on_heartbeat_error: Callable[[BaseException], None] | None = None,
) -> list[Command]:
    if interval < 0:
        raise ValueError("interval must be >= 0")
    if max_errors < 1:
        raise ValueError("max_errors must be >= 1")
    if retry_base < 0 or max_backoff < 0:
        raise ValueError("retry delays must be >= 0")
    if (heartbeat_interval is None) != (heartbeat is None):
        raise ValueError("heartbeat and heartbeat_interval must be set together")
    if heartbeat_interval is not None and heartbeat_interval <= 0:
        raise ValueError("heartbeat_interval must be > 0")

    consecutive_errors = 0
    next_heartbeat = (
        monotonic() + heartbeat_interval
        if heartbeat_interval is not None
        else None
    )
    while True:
        try:
            commands = transport.poll()
        except (Exception, SystemExit) as exc:
            consecutive_errors += 1
            if consecutive_errors >= max_errors:
                if on_error is not None:
                    on_error(exc, consecutive_errors, None)
                raise PollError(
                    f"poll failed {consecutive_errors} consecutive times"
                ) from exc
            delay = min(
                max_backoff,
                retry_base * (2 ** (consecutive_errors - 1)),
            )
            if on_error is not None:
                on_error(exc, consecutive_errors, delay)
            sleep(delay)
            continue

        consecutive_errors = 0
        if commands:
            return commands
        if (
            heartbeat is not None
            and heartbeat_interval is not None
            and next_heartbeat is not None
            and monotonic() >= next_heartbeat
        ):
            try:
                heartbeat()
            except (Exception, SystemExit) as exc:
                if on_heartbeat_error is not None:
                    on_heartbeat_error(exc)
            next_heartbeat = monotonic() + heartbeat_interval
        sleep(interval)
