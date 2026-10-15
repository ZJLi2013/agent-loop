from __future__ import annotations

import argparse
import json
import os
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
from harness.plan_review import (  # noqa: E402
    again_task,
    approve_task,
    respond_task,
    run_plan_review,
)
from harness.review import run_review  # noqa: E402


SESSION_ENV = ("AGENT_LOOP_SESSION_ID", "CURSOR_CONVERSATION_ID")


def _command(value: list[str]) -> list[str]:
    return value[1:] if value and value[0] == "--" else value


def _session_id() -> str | None:
    return next((os.environ[name] for name in SESSION_ENV if os.environ.get(name)), None)


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
    plan_review = commands.add_parser(
        "plan-review", help="review the tasks that have not been reviewed yet"
    )
    plan_review.add_argument("--plan-doc", required=True)
    human_choice = plan_review.add_mutually_exclusive_group()
    human_choice.add_argument(
        "--approve",
        metavar="TASK",
        help="record the human's decision on the task's human items",
    )
    human_choice.add_argument(
        "--again",
        metavar="TASK",
        help="record the human's request to review the task once more",
    )
    human_choice.add_argument(
        "--respond",
        metavar="TASK",
        help="record the executor's answers to the task's reviewer items",
    )
    plan_review.add_argument(
        "--item",
        action="append",
        default=[],
        help="N=applied|skipped|reject; repeatable, requires --respond",
    )
    plan_review.add_argument(
        "--reason",
        help="the human's words for --approve / --again, or the fact behind a reject",
    )
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
                owner=_session_id(),
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
            config, state = load_runtime(root)
            print(
                json.dumps(
                    {"result": result, "state": state},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            review = state.get("review") or {}
            review_passed = (
                not config.get("reviewer")
                or (
                    review.get("verify_run_id") == state.get("last_run_id")
                    and bool(review.get("decision"))
                )
            )
            return 0 if state["phase"] == "verified" and review_passed else 1
        if args.action == "review":
            outcome = run_review(root, objection=args.objection)
            print(json.dumps(outcome, ensure_ascii=False, indent=2))
            return 0 if outcome["review"]["decision"] else 1
        if args.action == "plan-review":
            if args.reason is not None and not (args.approve or args.again or args.respond):
                build_parser().error("--reason requires --approve, --again or --respond")
            if bool(args.item) != bool(args.respond):
                build_parser().error("--respond needs at least one --item, and --item needs --respond")
            reason = args.reason or ""
            if args.approve:
                outcome = approve_task(root, args.approve, reason=reason)
            elif args.again:
                outcome = again_task(root, args.again, reason=reason)
            elif args.respond:
                outcome = respond_task(root, args.respond, items=args.item, reason=args.reason)
            else:
                outcome = run_plan_review(root, plan_doc=args.plan_doc)
            print(json.dumps(outcome, ensure_ascii=False, indent=2))
            return 0
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

