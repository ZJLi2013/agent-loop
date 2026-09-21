#!/usr/bin/env python3
"""Observe the `stop` event: does it fire, and what does it carry?

Phase 1 is deliberately read-only. It returns {} so the agent is never fed
back in, and appends one line per firing to .cursor/hooks/stop-probe.log.

What we are trying to settle: the docs disagree with themselves. The event
list calls `stop` "handle agent completion" and `loop_limit` is documented
as "mainly for stop and subagentStop follow-up loops", but the output table
only grants `followup_message` to `subagentStop`. If `stop` does support it,
it is the Ralph primitive — the agent would no longer get to choose whether
to continue.

Phase 2 (only after this one is seen firing): return followup_message guarded
by a sentinel file, so a single test run cannot turn into a loop.
"""

import datetime
import json
import os
import sys

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stop-probe.log")


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    try:
        payload = json.loads(raw or "{}")
        keys = sorted(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
    except json.JSONDecodeError:
        keys = f"<unparseable {len(raw)}B>"

    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now().isoformat(timespec='seconds')}  keys={keys}\n")
            fh.write(f"  raw={raw[:800]}\n")
    except OSError:
        pass

    sys.stdout.write("{}")


if __name__ == "__main__":
    main()
