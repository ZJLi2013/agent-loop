from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable, Sequence

from pager.graph_transport import GraphTransport
from pager.protocol import Command, render_page
from pager.runner import PollError, listen
from pager.transport import Transport


TransportFactory = Callable[[str, Path], Transport]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--address", default=os.getenv("PAGER_CONTROL_ADDRESS")
    )
    common.add_argument(
        "--state",
        type=Path,
        default=Path(
            os.getenv(
                "PAGER_STATE_PATH",
                str(Path.home() / ".pager" / "state.json"),
            )
        ),
    )

    send = subparsers.add_parser("send", parents=[common])
    send.add_argument("--task-id", required=True)
    send.add_argument("--title", required=True)
    send.add_argument("--body", default="")

    notify = subparsers.add_parser("notify", parents=[common])
    notify.add_argument("--title", required=True)
    notify.add_argument("--body", default="")

    wait = subparsers.add_parser("wait", parents=[common])
    wait.add_argument("--timeout", type=float, default=600)
    wait.add_argument("--interval", type=float, default=10)

    serve = subparsers.add_parser("serve", parents=[common])
    serve.add_argument("--interval", type=float, default=10)
    serve.add_argument("--max-errors", type=int, default=3)
    serve.add_argument("--retry-base", type=float, default=5)
    serve.add_argument("--max-backoff", type=float, default=300)
    serve.add_argument("--heartbeat-seconds", type=float, default=3600)
    serve.add_argument("--heartbeat-title", default="listener alive")
    serve.add_argument("--heartbeat-body", default="last poll ok")
    return parser


def _load_graph_client():
    value = os.getenv("PAGER_GRAPH_SCRIPTS")
    if not value:
        raise SystemExit(
            "PAGER_GRAPH_SCRIPTS must point to a directory providing "
            "graph_client.GraphClient"
        )
    scripts = Path(value)
    if not scripts.is_dir():
        raise SystemExit(f"PAGER_GRAPH_SCRIPTS not found: {scripts}")
    sys.path.insert(0, str(scripts))
    from graph_client import GraphClient

    return GraphClient()


def _default_transport(address: str, state_path: Path) -> GraphTransport:
    return GraphTransport(
        _load_graph_client(),
        control_address=address,
        state_path=state_path,
    )


def _command_json(command: Command) -> dict[str, str]:
    return {
        "verb": command.verb.value,
        "task_id": command.task_id,
        "text": command.text,
    }


def _command_payload(commands: list[Command]) -> dict:
    return {
        "status": "command",
        "commands": [_command_json(command) for command in commands],
    }


def run(
    argv: Sequence[str] | None = None,
    *,
    transport_factory: TransportFactory = _default_transport,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    args = _parser().parse_args(argv)
    if not args.address:
        raise SystemExit(
            "PAGER_CONTROL_ADDRESS or --address is required"
        )
    transport = transport_factory(args.address, args.state)

    if args.command == "send":
        page = render_page(args.task_id, args.title, args.body)
        transport.send(page)
        print(json.dumps({"status": "sent", "task_id": page.task_id}))
        return 0

    if args.command == "notify":
        transport.notify(args.title, args.body)
        print(json.dumps({"status": "notified"}))
        return 0

    if args.command == "serve":
        if (
            args.interval <= 0
            or args.max_errors < 1
            or args.retry_base < 0
            or args.max_backoff < 0
            or args.heartbeat_seconds < 0
        ):
            raise SystemExit("invalid serve retry configuration")

        def report_error(
            error: BaseException, count: int, delay: float | None
        ) -> None:
            print(
                json.dumps(
                    {
                        "status": "poll_error",
                        "error": str(error),
                        "consecutive_errors": count,
                        "retry_in": delay,
                    }
                ),
                file=sys.stderr,
            )

        def report_heartbeat_error(error: BaseException) -> None:
            print(
                json.dumps(
                    {"status": "heartbeat_error", "error": str(error)}
                ),
                file=sys.stderr,
            )

        heartbeat = (
            lambda: transport.notify(
                args.heartbeat_title, args.heartbeat_body
            )
            if args.heartbeat_seconds > 0
            else None
        )
        try:
            commands = listen(
                transport,
                interval=args.interval,
                max_errors=args.max_errors,
                retry_base=args.retry_base,
                max_backoff=args.max_backoff,
                sleep=sleep,
                monotonic=monotonic,
                heartbeat_interval=(
                    args.heartbeat_seconds
                    if args.heartbeat_seconds > 0
                    else None
                ),
                heartbeat=heartbeat,
                on_error=report_error,
                on_heartbeat_error=report_heartbeat_error,
            )
        except PollError as exc:
            print(
                json.dumps({"status": "error", "error": str(exc)}),
                file=sys.stderr,
            )
            return 1
        print(json.dumps(_command_payload(commands)))
        return 0

    if args.timeout < 0 or args.interval <= 0:
        raise SystemExit("--timeout must be >= 0 and --interval must be > 0")
    deadline = monotonic() + args.timeout
    while True:
        commands = transport.poll()
        if commands:
            print(json.dumps(_command_payload(commands)))
            return 0
        remaining = deadline - monotonic()
        if remaining <= 0:
            print(json.dumps({"status": "timeout"}))
            return 2
        sleep(min(args.interval, remaining))


def main() -> None:
    raise SystemExit(run())
