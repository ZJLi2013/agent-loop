from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

HARNESS_DIR = ".harness"
CONFIG_FILE = "config.json"
STATE_FILE = "state.json"
JOURNAL_FILE = "runs.jsonl"
LOCK_FILE = "lock"

DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MAX_WALL_SECONDS = 1800.0
DEFAULT_MAX_OUTPUT_BYTES = 1_048_576
DEFAULT_MAX_ARTIFACTS = 20
DEFAULT_MAX_JOURNAL_ENTRIES = 1000

_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|password|secret|authorization)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)


class HarnessError(RuntimeError):
    pass


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


def initialize(
    root: Path,
    *,
    task_id: str,
    verifier_argv: list[str],
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_wall_seconds: float = DEFAULT_MAX_WALL_SECONDS,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    max_artifacts: int = DEFAULT_MAX_ARTIFACTS,
    max_journal_entries: int = DEFAULT_MAX_JOURNAL_ENTRIES,
    expect_regex: str | None = None,
    forbid_regex: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not task_id.strip():
        raise HarnessError("task_id is required")
    if not verifier_argv:
        raise HarnessError("verifier command is required")
    for label, pattern in (
        ("expect_regex", expect_regex),
        ("forbid_regex", forbid_regex),
    ):
        if pattern:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise HarnessError(f"invalid {label}: {exc}") from exc
    if min(
        timeout_seconds,
        max_attempts,
        max_wall_seconds,
        max_output_bytes,
        max_artifacts,
        max_journal_entries,
    ) <= 0:
        raise HarnessError("timeouts, budgets, and limits must be positive")

    base = harness_dir(root)
    state_path = base / STATE_FILE
    if state_path.exists():
        old = read_json(state_path)
        if old.get("active") and old.get("phase") not in {"verified", "stopped"}:
            raise HarnessError(
                f"task {old.get('task_id')} is still active; finish or disable it first"
            )

    created_at = utc_now()
    config: dict[str, Any] = {
        "version": 1,
        "task_id": task_id,
        "verifier": {
            "argv": verifier_argv,
            "timeout_seconds": float(timeout_seconds),
            "expect_regex": expect_regex,
            "forbid_regex": forbid_regex,
        },
        "budget": {
            "max_attempts": int(max_attempts),
            "max_wall_seconds": float(max_wall_seconds),
        },
        "limits": {
            "max_output_bytes": int(max_output_bytes),
            "max_artifacts": int(max_artifacts),
            "max_journal_entries": int(max_journal_entries),
        },
        "created_at": created_at,
    }
    state: dict[str, Any] = {
        "version": 1,
        "task_id": task_id,
        "active": True,
        "phase": "ready",
        "verify_attempts": 0,
        "wall_seconds_used": 0.0,
        "current_run_id": None,
        "last_run_id": None,
        "last_outcome": None,
        "verified_fingerprint": None,
        "stop_report_requested": False,
        "config_sha256": config_digest(config),
        "created_at": created_at,
        "updated_at": created_at,
    }
    base.mkdir(parents=True, exist_ok=True)
    atomic_write_json(base / CONFIG_FILE, config)
    atomic_write_json(state_path, state)
    (base / "artifacts").mkdir(exist_ok=True)
    _exclude_runtime_from_git(root)
    return config, state


def _exclude_runtime_from_git(root: Path) -> None:
    git_dir = root.resolve() / ".git"
    if not git_dir.is_dir():
        return
    exclude = git_dir / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    current = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    entry = f"/{HARNESS_DIR}/"
    if entry not in current.splitlines():
        separator = "" if not current or current.endswith("\n") else "\n"
        with exclude.open("a", encoding="utf-8") as fh:
            fh.write(f"{separator}{entry}\n")


def _new_run_id() -> str:
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def _kill_process_tree(proc: subprocess.Popen[Any]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            proc.kill()
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=5)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bounded_text(path: Path, cap: int) -> tuple[str, bool]:
    size = path.stat().st_size
    if size <= cap:
        data = path.read_bytes()
        truncated = False
    else:
        half = max(1, cap // 2)
        with path.open("rb") as fh:
            head = fh.read(half)
            fh.seek(max(0, size - half))
            tail = fh.read(half)
        data = head + b"\n... output truncated ...\n" + tail
        truncated = True
    text = data.decode("utf-8", errors="replace")
    return _SECRET_RE.sub(r"\1\2***REDACTED***", text), truncated


def _write_artifact(
    destination: Path,
    source: Path,
    cap: int,
) -> tuple[str, bool]:
    text, truncated = _bounded_text(source, cap)
    destination.write_text(text, encoding="utf-8")
    return _sha256_file(source), truncated


def _remaining_wall(config: dict[str, Any], state: dict[str, Any]) -> float:
    maximum = float(config["budget"]["max_wall_seconds"])
    return maximum - float(state["wall_seconds_used"])


def _budget_exhausted(
    config: dict[str, Any],
    state: dict[str, Any],
) -> bool:
    return (
        int(state["verify_attempts"]) >= int(config["budget"]["max_attempts"])
        or _remaining_wall(config, state) <= 0
    )


def run_command(
    root: Path,
    argv: list[str],
    *,
    kind: str,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    if not argv:
        raise HarnessError("command is required")
    if kind not in {"exec", "verify"}:
        raise HarnessError(f"unsupported run kind: {kind}")

    root = root.resolve()
    with state_lock(root):
        config, state = load_runtime(root)
        if not state.get("active"):
            raise HarnessError("harness is disabled")
        if _budget_exhausted(config, state):
            state["phase"] = "stopped"
            state["updated_at"] = utc_now()
            atomic_write_json(harness_dir(root) / STATE_FILE, state)
            raise HarnessError("execution budget exhausted")

        remaining = _remaining_wall(config, state)
        requested = (
            float(timeout_seconds)
            if timeout_seconds is not None
            else float(config["verifier"]["timeout_seconds"])
        )
        if requested <= 0:
            raise HarnessError("timeout must be positive")
        timeout = min(requested, remaining)
        run_id = _new_run_id()
        run_dir = harness_dir(root) / "artifacts" / run_id
        run_dir.mkdir(parents=True)
        state["phase"] = "verifying" if kind == "verify" else "running"
        state["current_run_id"] = run_id
        state["updated_at"] = utc_now()
        atomic_write_json(harness_dir(root) / STATE_FILE, state)

        started_at = utc_now()
        start = time.monotonic()
        timed_out = False
        error: str | None = None
        exit_code: int | None = None

        with tempfile.TemporaryDirectory(prefix="agent-loop-harness-") as temp_dir:
            raw_stdout = Path(temp_dir) / "stdout"
            raw_stderr = Path(temp_dir) / "stderr"
            try:
                with raw_stdout.open("wb") as stdout_fh, raw_stderr.open(
                    "wb"
                ) as stderr_fh:
                    kwargs: dict[str, Any] = {
                        "cwd": root,
                        "stdout": stdout_fh,
                        "stderr": stderr_fh,
                        "stdin": subprocess.DEVNULL,
                    }
                    if os.name == "nt":
                        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                    else:
                        kwargs["start_new_session"] = True
                    proc = subprocess.Popen(argv, **kwargs)
                    try:
                        exit_code = proc.wait(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        _kill_process_tree(proc)
            except OSError as exc:
                error = str(exc)
                raw_stdout.touch(exist_ok=True)
                raw_stderr.touch(exist_ok=True)

            duration = time.monotonic() - start
            cap = int(config["limits"]["max_output_bytes"])
            stdout_hash, stdout_truncated = _write_artifact(
                run_dir / "stdout.log", raw_stdout, cap
            )
            stderr_hash, stderr_truncated = _write_artifact(
                run_dir / "stderr.log", raw_stderr, cap
            )

        outcome = (
            "timeout"
            if timed_out
            else "error"
            if error
            else "pass"
            if exit_code == 0
            else "fail"
        )
        result: dict[str, Any] = {
            "version": 1,
            "run_id": run_id,
            "task_id": state["task_id"],
            "kind": kind,
            "argv": argv,
            "cwd": str(root),
            "started_at": started_at,
            "finished_at": utc_now(),
            "duration_seconds": round(duration, 6),
            "timeout_seconds": timeout,
            "timed_out": timed_out,
            "exit_code": exit_code,
            "error": error,
            "outcome": outcome,
            "stdout_sha256": stdout_hash,
            "stderr_sha256": stderr_hash,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }
        state["wall_seconds_used"] = round(
            float(state["wall_seconds_used"]) + duration, 6
        )
        state["current_run_id"] = None
        state["last_run_id"] = run_id
        if kind == "verify":
            state["verify_attempts"] = int(state["verify_attempts"]) + 1
            contract_passed = outcome == "pass" and _matches_contract(
                config, run_dir
            )
            result["verification_passed"] = contract_passed
            if contract_passed:
                state["phase"] = "verified"
                state["verified_fingerprint"] = workspace_fingerprint(root)
            else:
                if outcome == "pass":
                    result["outcome"] = "reject"
                state["phase"] = (
                    "stopped" if _budget_exhausted(config, state) else "failed"
                )
                state["verified_fingerprint"] = None
        else:
            state["phase"] = (
                "stopped" if _budget_exhausted(config, state) else "ready"
            )
        state["last_outcome"] = result["outcome"]
        state["updated_at"] = utc_now()
        atomic_write_json(run_dir / "result.json", result)
        atomic_write_json(harness_dir(root) / STATE_FILE, state)
        _append_journal(root, result, int(config["limits"]["max_journal_entries"]))
        _prune_artifacts(root, int(config["limits"]["max_artifacts"]))
        return result


def _matches_contract(
    config: dict[str, Any],
    run_dir: Path,
) -> bool:
    verifier = config["verifier"]
    expect = verifier.get("expect_regex")
    forbid = verifier.get("forbid_regex")
    if not expect and not forbid:
        return True
    output = (
        (run_dir / "stdout.log").read_text(encoding="utf-8")
        + "\n"
        + (run_dir / "stderr.log").read_text(encoding="utf-8")
    )
    if expect:
        if not re.search(str(expect), output, flags=re.MULTILINE):
            return False
    if forbid:
        if re.search(str(forbid), output, flags=re.MULTILINE):
            return False
    return True


def verify(root: Path) -> dict[str, Any]:
    config, _ = load_runtime(root)
    verifier = config["verifier"]
    return run_command(
        root,
        list(verifier["argv"]),
        kind="verify",
        timeout_seconds=float(verifier["timeout_seconds"]),
    )


def _append_journal(root: Path, result: dict[str, Any], limit: int) -> None:
    path = harness_dir(root) / JOURNAL_FILE
    summary = {
        key: result[key]
        for key in (
            "run_id",
            "task_id",
            "kind",
            "argv",
            "started_at",
            "duration_seconds",
            "timed_out",
            "exit_code",
            "outcome",
        )
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary, ensure_ascii=False) + "\n")
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) > limit:
        path.write_text("\n".join(lines[-limit:]) + "\n", encoding="utf-8")


def _prune_artifacts(root: Path, limit: int) -> None:
    artifacts = harness_dir(root) / "artifacts"
    runs = sorted(
        (path for path in artifacts.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    )
    for old in runs[:-limit]:
        shutil.rmtree(old, ignore_errors=True)


def workspace_fingerprint(root: Path) -> str:
    root = root.resolve()
    digest = hashlib.sha256()
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD", "--", ".", f":(exclude){HARNESS_DIR}"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")
        digest.update(head)
        digest.update(diff)
        for raw_path in sorted(path for path in untracked if path):
            relative = raw_path.decode("utf-8", errors="surrogateescape")
            if relative == HARNESS_DIR or relative.startswith(f"{HARNESS_DIR}/"):
                continue
            digest.update(raw_path)
            path = root / relative
            if path.is_file():
                with path.open("rb") as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                        digest.update(chunk)
        return digest.hexdigest()
    except (OSError, subprocess.CalledProcessError):
        return _fallback_fingerprint(root)


def _fallback_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not path.is_file() or relative.parts[0] in {HARNESS_DIR, ".git"}:
            continue
        digest.update(str(relative).encode("utf-8", errors="surrogateescape"))
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def disable(root: Path) -> dict[str, Any]:
    with state_lock(root):
        state = read_json(harness_dir(root) / STATE_FILE)
        state["active"] = False
        state["phase"] = "stopped"
        state["updated_at"] = utc_now()
        atomic_write_json(harness_dir(root) / STATE_FILE, state)
        return state


def completion_gate(root: Path) -> str | None:
    state_path = harness_dir(root) / STATE_FILE
    if not state_path.exists():
        return None
    with state_lock(root):
        try:
            config, state = load_runtime(root)
        except HarnessError as exc:
            return f"Harness state is invalid: {exc}. Repair it before completing."
        if not state.get("active"):
            return None

        phase = state.get("phase")
        if phase == "verified":
            if state.get("verified_fingerprint") == workspace_fingerprint(root):
                return None
            state["phase"] = "failed"
            state["verified_fingerprint"] = None
            state["last_outcome"] = "stale"
            state["updated_at"] = utc_now()
            atomic_write_json(state_path, state)
            return (
                f"Harness verification for {state['task_id']} is stale because the "
                "workspace changed. Run the locked verifier again."
            )

        if phase == "stopped":
            if state.get("stop_report_requested"):
                return None
            state["stop_report_requested"] = True
            state["updated_at"] = utc_now()
            atomic_write_json(state_path, state)
            return (
                f"Harness budget for {state['task_id']} is exhausted. Do not retry. "
                "Write an Auto-Stop Report with the current position, attempts, "
                "and the first command for returning to the main path, then stop."
            )

        remaining_attempts = int(config["budget"]["max_attempts"]) - int(
            state["verify_attempts"]
        )
        remaining_wall = max(0.0, _remaining_wall(config, state))
        runner = Path.home() / ".cursor" / "harness" / "run.py"
        verify_command = (
            f'python "{runner}" --root "{root.resolve()}" verify'
        )
        if phase in {"running", "verifying"}:
            state["phase"] = "failed"
            state["current_run_id"] = None
            state["last_outcome"] = "interrupted"
            state["updated_at"] = utc_now()
            atomic_write_json(state_path, state)
        return (
            f"Task {state['task_id']} is not independently verified "
            f"({remaining_attempts} attempts, {remaining_wall:.1f}s remain). "
            f"Diagnose or repair if needed, then run: {verify_command}"
        )

