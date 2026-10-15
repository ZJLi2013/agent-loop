from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterator

from harness.errors import HarnessError

HARNESS_DIR = ".harness"
CONFIG_FILE = "config.json"
STATE_FILE = "state.json"
JOURNAL_FILE = "runs.jsonl"
LOCK_FILE = "lock"
LOCK_WAIT_SECONDS = 5.0


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def harness_dir(root: Path) -> Path:
    return root.resolve() / HARNESS_DIR


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise HarnessError(f"{path} must contain a JSON object")
    return value


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, path)


def config_digest(config: dict[str, Any]) -> str:
    encoded = json.dumps(
        config, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def pid_alive(pid: int) -> bool:
    # On Windows os.kill(pid, 0) terminates the process instead of probing it.
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # access denied: the process exists
        code = ctypes.c_ulong()
        try:
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _lock_holder(lock_path: Path) -> str:
    try:
        text = lock_path.read_text(encoding="utf-8").strip()
    except OSError:
        return f"{lock_path} exists"
    try:
        holder = json.loads(text)
    except json.JSONDecodeError:
        holder = {"pid": text}
    if not isinstance(holder, dict):
        holder = {"pid": holder}
    pid = holder.get("pid")
    message = (
        f"{lock_path} is held by pid {pid} ({' '.join(holder.get('argv') or []) or 'command unknown'}) "
        f"since {holder.get('started_at') or 'an unknown time'}"
    )
    if isinstance(pid, (int, str)) and str(pid).isdigit() and not pid_alive(int(pid)):
        remove = f'Remove-Item "{lock_path}"' if os.name == "nt" else f'rm "{lock_path}"'
        message += f"; that process is gone, so the lock is stale. Remove it with: {remove}"
    return message


@contextlib.contextmanager
def state_lock(root: Path, *, wait_seconds: float = LOCK_WAIT_SECONDS) -> Iterator[None]:
    lock_path = harness_dir(root) / LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise HarnessError(_lock_holder(lock_path)) from None
            time.sleep(0.1)
    try:
        holder = {"pid": os.getpid(), "argv": sys.argv, "started_at": utc_now()}
        os.write(fd, json.dumps(holder, ensure_ascii=False).encode("utf-8"))
        os.close(fd)
        yield
    finally:
        with contextlib.suppress(OSError):
            lock_path.unlink()


def load_runtime(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    base = harness_dir(root)
    config = read_json(base / CONFIG_FILE)
    state = read_json(base / STATE_FILE)
    if state.get("config_sha256") != config_digest(config):
        raise HarnessError(
            "config.json changed after init; reinitialize only after this task stops"
        )
    return config, state

