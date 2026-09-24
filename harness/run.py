from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.attention import record_goal_review  # noqa: E402
from harness.core import (  # noqa: E402
    DEFAULT_MAX_ARTIFACTS,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MAX_JOURNAL_ENTRIES,
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_MAX_WALL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    HarnessError,
    disable,
    initialize,
    load_runtime,
    pause_request,
    request_pause,
    resume,
    run_command,
    verify,
)
from harness.page import run_page  # noqa: E402
from harness.review import run_review  # noqa: E402


def _command(value: list[str]) -> list[str]:
    return value[1:] if value and value[0] == "--" else value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-loop-harness")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="project root (default: current directory)",
    )
    commands = parser.add_subparsers(dest="action", required=True)

    init = commands.add_parser("init", help="activate the harness for one task")
    init.add_argument("--task", required=True)
    init.add_argument(
        "--plan-doc",
        dest="plan_doc",
        help="plan document path relative to project root",
    )
    init.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    init.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    init.add_argument(
        "--max-wall-seconds", type=float, default=DEFAULT_MAX_WALL_SECONDS
    )
    init.add_argument(
        "--max-output-bytes", type=int, default=DEFAULT_MAX_OUTPUT_BYTES
    )
    init.add_argument("--max-artifacts", type=int, default=DEFAULT_MAX_ARTIFACTS)
    init.add_argument(
        "--max-journal-entries",
        type=int,
        default=DEFAULT_MAX_JOURNAL_ENTRIES,
    )
    init.add_argument("--goal-review-actions", type=int, default=3)
    init.add_argument("--goal-review-minutes", type=float, default=60.0)
    init.add_argument(
        "--no-goal-review-on-failure",
        action="store_false",
        dest="goal_review_on_failure",
    )
    init.add_argument("--expect-regex")
    init.add_argument("--forbid-regex")
    init.add_argument("verifier", nargs=argparse.REMAINDER)

    execute = commands.add_parser("exec", help="run and journal one command")
    execute.add_argument("--timeout", type=float)
    execute.add_argument("command", nargs=argparse.REMAINDER)

    commands.add_parser("verify", help="run the locked verifier")
    review = commands.add_parser(
        "review", help="run the configured reviewer at the task boundary"
    )
    review.add_argument("--objection", help="one factual error in the last decision")
    commands.add_parser(
        "page", help="send the pending human checkpoint to the phone and wait"
    )
    pause = commands.add_parser("pause", help="pause before the next action")
    pause.add_argument("--reason", required=True)
    pause.add_argument("--require-revision", action="store_true")
    commands.add_parser("resume", help="resume after plan review")
    goal_review = commands.add_parser(
        "goal-review", help="record attention refresh decision"
    )
    goal_review.add_argument(
        "--decision", choices=("continue", "replan", "stop"), required=True
    )
    goal_review.add_argument("--evidence", required=True)
    commands.add_parser("status", help="print current config and state")
    commands.add_parser("disable", help="stop automatic completion gating")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    try:
        if args.action == "init":
            config, state = initialize(
                root,
                task_id=args.task,
                verifier_argv=_command(args.verifier),
                plan_doc=args.plan_doc,
                timeout_seconds=args.timeout,
                max_attempts=args.max_attempts,
                max_wall_seconds=args.max_wall_seconds,
                max_output_bytes=args.max_output_bytes,
                max_artifacts=args.max_artifacts,
                max_journal_entries=args.max_journal_entries,
                goal_review_after_actions=args.goal_review_actions,
                goal_review_after_seconds=args.goal_review_minutes * 60,
                goal_review_on_failure=args.goal_review_on_failure,
                expect_regex=args.expect_regex,
                forbid_regex=args.forbid_regex,
            )
            print(
                json.dumps(
                    {"config": config, "state": state},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.action == "exec":
            result = run_command(
                root,
                _command(args.command),
                kind="exec",
                timeout_seconds=args.timeout,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["outcome"] == "pass" else 1
        if args.action == "verify":
            result = verify(root)
            _, state = load_runtime(root)
            print(
                json.dumps(
                    {"result": result, "state": state},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0 if state["phase"] == "verified" else 1
        if args.action == "review":
            outcome = run_review(root, objection=args.objection)
            print(json.dumps(outcome, ensure_ascii=False, indent=2))
            return 0 if outcome["review"]["decision"] else 1
        if args.action == "page":
            outcome = run_page(root)
            print(json.dumps(outcome, ensure_ascii=False, indent=2))
            return 0
        if args.action == "pause":
            request = request_pause(
                root,
                reason=args.reason,
                require_revision=args.require_revision,
            )
            print(json.dumps(request, ensure_ascii=False, indent=2))
            return 0
        if args.action == "resume":
            state = resume(root)
            print(json.dumps(state, ensure_ascii=False, indent=2))
            return 0
        if args.action == "goal-review":
            state = record_goal_review(
                root,
                decision=args.decision,
                evidence=args.evidence,
            )
            print(json.dumps(state, ensure_ascii=False, indent=2))
            return 0
        if args.action == "status":
            config, state = load_runtime(root)
            print(
                json.dumps(
                    {
                        "config": config,
                        "state": state,
                        "pause": pause_request(root),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        state = disable(root)
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0
    except HarnessError as exc:
        print(f"harness: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

