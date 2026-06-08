#!/usr/bin/env python3
"""Run one non-interactive SSH command through Paramiko.

Use this on Windows/Conductor GPU nodes when OpenSSH hangs during publickey
authentication from an agent process.
"""

from __future__ import annotations

import argparse
import sys
import time

import paramiko


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-delay", type=float, default=2.0)
    cmd_group = parser.add_mutually_exclusive_group(required=True)
    cmd_group.add_argument("--cmd")
    cmd_group.add_argument("--cmd-file")
    args = parser.parse_args()
    command = args.cmd
    if args.cmd_file:
        with open(args.cmd_file, "r", encoding="utf-8-sig") as f:
            command = f.read()

    key = paramiko.Ed25519Key.from_private_key_file(args.key)
    attempts = max(1, args.retries + 1)
    last_exc: Exception | None = None
    for attempt in range(attempts):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=args.host,
                username=args.user,
                pkey=key,
                timeout=args.timeout,
                banner_timeout=args.timeout,
                auth_timeout=args.timeout,
                look_for_keys=False,
                allow_agent=False,
            )
            _stdin, stdout, stderr = client.exec_command(command, timeout=args.timeout)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            if out:
                sys.stdout.buffer.write(out.encode("utf-8", "replace"))
            if err:
                sys.stderr.buffer.write(err.encode("utf-8", "replace"))
            return int(stdout.channel.recv_exit_status())
        except Exception as exc:
            last_exc = exc
            if attempt + 1 >= attempts:
                break
            time.sleep(args.retry_delay)
        finally:
            client.close()
    print(f"ssh_paramiko failed after {attempts} attempt(s): {last_exc}", file=sys.stderr)
    return 255


if __name__ == "__main__":
    raise SystemExit(main())
