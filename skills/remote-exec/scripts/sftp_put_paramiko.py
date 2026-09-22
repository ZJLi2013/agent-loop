#!/usr/bin/env python3
"""Upload one or more local files to a remote host through Paramiko SFTP.

Counterpart to ``sftp_get_paramiko.py``. Use on Windows/Conductor GPU nodes
where remote ``git pull`` is blocked and changed files must be synced directly.

Each ``--pair`` is ``LOCAL_PATH::REMOTE_PATH``. Remote parent dirs are created.
"""

from __future__ import annotations

import argparse
import posixpath

import paramiko


def _ensure_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    parts = [p for p in remote_dir.split("/") if p]
    cur = "/" if remote_dir.startswith("/") else ""
    for part in parts:
        cur = posixpath.join(cur, part) if cur else part
        try:
            sftp.stat(cur)
        except IOError:
            sftp.mkdir(cur)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--pair",
        action="append",
        required=True,
        help="LOCAL_PATH::REMOTE_PATH (repeatable)",
    )
    args = parser.parse_args()

    key = paramiko.Ed25519Key.from_private_key_file(args.key)
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
        sftp = client.open_sftp()
        try:
            for pair in args.pair:
                local, remote = pair.split("::", 1)
                _ensure_remote_dir(sftp, posixpath.dirname(remote))
                sftp.put(local, remote)
                print(f"{local} -> {remote}")
        finally:
            sftp.close()
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
