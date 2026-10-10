from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from harness.errors import HarnessError
from harness.fingerprint import workspace_fingerprint
from harness.journal import append_journal, new_run_id, prune_artifacts
from harness.plan import plan_metadata
from harness.project import task_file
from harness.review import load_reviewer
from harness.runner import execute_process
from harness.storage import (
    atomic_write_json,
    harness_dir,
    read_json,
    state_lock,
    utc_now,
)

PLAN_REVIEW_DIR = "plan-review"
VERDICTS = ("accept", "revise")
DEFAULT_MAX_OUTPUT_BYTES = 1_048_576
DEFAULT_MAX_ARTIFACTS = 20
DEFAULT_MAX_JOURNAL_ENTRIES = 1000

PROMPT = """# Plan revision review

你是 plan reviewer。只审提交的 Plan Revision，不执行 task、不修改 workspace。

## 输入

- plan document：`{plan_doc}`
- task 列表：`{task_doc}`
- revision：`r{revision}`

按需打开 plan / task 直接引用的证据。

## 要做的事

1. 检查最近 1–2 个 proposed task 是否各自链接本地设计文档；plan 表格里的一行不算设计。
2. 检查每个 task 的验收判据能否支持它声称的结论，成立与不成立是否指向不同的下一动作。
3. 检查昂贵动作前是否缺少能改变选择的廉价前置。
4. 研究型 task（方法是否有效、现象成因、方案选型）缺少领域先例，或设计与已知结论冲突却未说明
   理由，报 revise。
5. 只报告会改变 human 批准、task 拆分或第一条执行命令的问题。

你不能批准 plan、改变 task 状态、关闭 task 或选择 successor。最终决定属于 human。
不要修改 plan、task 或代码。

## 输出

把下面的 JSON 写到 `{report_file}`：

```json
{{"verdict": "accept | revise", "summary": "<一句话>", "findings": ["<只列会改变决定的问题>"]}}
```
"""


def _plan_path(root: Path, plan_doc: str) -> tuple[Path, str]:
    root = root.resolve()
    path = (root / plan_doc).resolve()
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise HarnessError("plan document must be inside the project root") from exc
    if not path.is_file():
        raise HarnessError(f"plan document does not exist: {relative}")
    return path, relative


def _review_key(plan_doc: str, revision: int) -> str:
    digest = hashlib.sha256(plan_doc.encode()).hexdigest()[:12]
    return f"{digest}-r{revision}"


def _review_dir(root: Path) -> Path:
    return harness_dir(root) / PLAN_REVIEW_DIR


def _read_report(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "plan reviewer did not write report"
    try:
        value = read_json(path)
    except HarnessError as exc:
        return None, str(exc)
    verdict = value.get("verdict")
    summary = value.get("summary")
    findings = value.get("findings")
    if verdict not in VERDICTS:
        return None, f"verdict must be one of {', '.join(VERDICTS)}"
    if not isinstance(summary, str) or not summary.strip():
        return None, "summary is required"
    if not isinstance(findings, list) or not all(
        isinstance(item, str) and item.strip() for item in findings
    ):
        return None, "findings must be a list of non-empty strings"
    if verdict == "revise" and not findings:
        return None, "revise requires at least one finding"
    return {
        "verdict": verdict,
        "summary": summary.strip(),
        "findings": [item.strip() for item in findings],
    }, None


def plan_review_record(
    root: Path, plan_doc: str, revision: int
) -> dict[str, Any] | None:
    _, relative = _plan_path(root, plan_doc)
    path = _review_dir(root) / f"{_review_key(relative, revision)}.json"
    if not path.exists():
        return None
    value = read_json(path)
    if value.get("plan_doc") != relative or value.get("revision") != revision:
        raise HarnessError(f"invalid plan review record: {path}")
    return value


def plan_review_ready(
    root: Path, plan_doc: str, revision: int
) -> tuple[bool, str | None]:
    record = plan_review_record(root, plan_doc, revision)
    if not record:
        return False, f"Plan Revision {revision} has no independent review"
    if record.get("error"):
        return False, f"Plan Revision {revision} review failed: {record['error']}"
    return True, None


def run_plan_review(
    root: Path,
    *,
    plan_doc: str,
    reviewer_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    reviewer = reviewer_config or load_reviewer(root)
    if not reviewer:
        raise HarnessError("no reviewer configured")
    _, relative = _plan_path(root, plan_doc)
    revision, _ = plan_metadata(root, relative)
    if revision is None:
        raise HarnessError("plan document must define Plan Revision")

    with state_lock(root):
        existing = plan_review_record(root, relative, revision)
        if existing:
            if existing.get("error"):
                raise HarnessError(
                    f"plan review r{revision} is incomplete: {existing['error']}"
                )
            return existing

        review_dir = _review_dir(root)
        review_dir.mkdir(parents=True, exist_ok=True)
        key = _review_key(relative, revision)
        report_path = review_dir / "report.json"
        prompt_path = harness_dir(root) / "review" / "prompt.md"
        record_path = review_dir / f"{key}.json"
        report_path.unlink(missing_ok=True)
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(
            PROMPT.format(
                plan_doc=relative,
                task_doc=task_file(root).resolve().relative_to(root).as_posix(),
                revision=revision,
                report_file=report_path.resolve().relative_to(root).as_posix(),
            ),
            encoding="utf-8",
        )

        before = workspace_fingerprint(root)
        run_id = new_run_id()
        run_dir = harness_dir(root) / "artifacts" / run_id
        run_dir.mkdir(parents=True)
        execution = execute_process(
            root,
            list(reviewer["argv"]),
            timeout_seconds=float(reviewer["timeout_seconds"]),
            run_dir=run_dir,
            max_output_bytes=DEFAULT_MAX_OUTPUT_BYTES,
            is_paused=lambda: False,
        )
        after = workspace_fingerprint(root)
        report, error = (
            _read_report(report_path)
            if execution["outcome"] == "pass"
            else (None, f"plan reviewer {execution['outcome']}")
        )
        if before != after:
            report = None
            error = "plan reviewer modified the workspace"

        record: dict[str, Any] = {
            "version": 1,
            "plan_doc": relative,
            "revision": revision,
            "run_id": run_id,
            "verdict": None,
            "summary": None,
            "findings": [],
            "error": error,
            "at": utc_now(),
        }
        if report:
            record.update(report)
        result = {
            "version": 1,
            "run_id": run_id,
            "task_id": f"plan:r{revision}",
            "kind": "plan_review",
            "argv": list(reviewer["argv"]),
            "plan_doc": relative,
            "revision": revision,
            **execution,
            "review": record,
        }
        atomic_write_json(record_path, record)
        atomic_write_json(run_dir / "result.json", result)
        append_journal(root, result, DEFAULT_MAX_JOURNAL_ENTRIES)
        prune_artifacts(root, DEFAULT_MAX_ARTIFACTS)
        if error:
            raise HarnessError(f"plan review r{revision} failed: {error}")
        return record
