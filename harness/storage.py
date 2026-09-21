from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterator

from harness.errors import HarnessError

HARNESS_DIR = ".harness"
CONFIG_FILE = "config.json"
STATE_FILE = "state.json"
JOURNAL_FILE = "runs.jsonl"
LOCK_FILE = "lock"


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


@contextlib.contextmanager
def state_lock(root: Path) -> Iterator[None]:
    lock_path = harness_dir(root) / LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise HarnessError(
            f"{lock_path} exists; another run may be active"
        ) from exc
    try:
        os.write(fd, f"{os.getpid()}\n".encode())
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

