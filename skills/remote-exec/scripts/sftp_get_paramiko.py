#!/usr/bin/env python3
"""Download one remote file or directory through Paramiko SFTP."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import paramiko


def _download_dir(sftp: paramiko.SFTPClient, remote: str, local: Path) -> None:
    local.mkdir(parents=True, exist_ok=True)
    for entry in sftp.listdir_attr(remote):
        rpath = f"{remote.rstrip('/')}/{entry.filename}"
        lpath = local / entry.filename
        if entry.st_mode is not None and (entry.st_mode & 0o170000) == 0o040000:
            _download_dir(sftp, rpath, lpath)
        else:
            lpath.parent.mkdir(parents=True, exist_ok=True)
            sftp.get(rpath, str(lpath))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--local", required=True)
    args = parser.parse_args()

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        key = paramiko.Ed25519Key.from_private_key_file(args.key)
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
            local = Path(args.local)
            mode = sftp.stat(args.remote).st_mode
            if mode is not None and (mode & 0o170000) == 0o040000:
                _download_dir(sftp, args.remote, local)
            else:
                local.parent.mkdir(parents=True, exist_ok=True)
                sftp.get(args.remote, str(local))
        finally:
            sftp.close()
    finally:
        client.close()
    print(os.fspath(Path(args.local)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
