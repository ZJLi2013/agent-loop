from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from adapters.protocol import HookAction, HookEvent, HookRequest, HookResponse
from harness.core import HarnessError, completion_gate
from harness.plan import request_pause
from harness.project import LEGACY_RUNTIME_DIR, RUNTIME_DIR, memory_dir

TRIGGER = "task.md"
STORES = ("facts.md", "episodes.md", "lessons.md")
MAX_HITS = 5
INDEX_MAX_LINES = 30
STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "有", "的", "了",
    "把", "在", "是", "和", "到", "个", "不", "要", "还", "会", "已", "做",
}


def _workspace_root(value: str | Path) -> Path:
    text = str(value)
    if os.name == "nt" and re.match(r"^/[A-Za-z]:/", text):
        text = text[1:]
    return Path(text)


def workspace_roots(values: Any) -> tuple[Path, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(_workspace_root(value) for value in values if isinstance(value, str))


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _find_path(payload: Any) -> Path | None:
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, str) and node.lower().endswith(".md"):
            return Path(node)
    return None


def _terms(task_md: str) -> set[str]:
    lines = [
        line for line in task_md.splitlines()
        if "🔬" in line or line.startswith("## Goal") or line.startswith("<一句话")
    ]
    all_lines = task_md.splitlines()
    goal_idx = next(
        (i for i, line in enumerate(all_lines) if line.startswith("## Goal")),
        -1,
    )
    if goal_idx >= 0:
        lines.extend(all_lines[goal_idx + 1:goal_idx + 3])
    words = re.findall(
        r"[A-Za-z][A-Za-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}",
        " ".join(lines),
    )
    return {word.lower() for word in words if word.lower() not in STOPWORDS}


def _hits(terms: set[str], memory: Path) -> list[str]:
    scored = []
    for store in STORES:
        for line in _read(memory / store).splitlines():
            stripped = line.strip()
            if not stripped.startswith("-") or len(stripped) < 8:
                continue
            score = sum(1 for term in terms if term in stripped.lower())
            if score:
                scored.append((score, f"{store}: {stripped.lstrip('- ')}"))
    scored.sort(key=lambda pair: -pair[0])
    return [text for _, text in scored[:MAX_HITS]]


def _health(memory: Path) -> str:
    counts = []
    for store in STORES:
        count = sum(
            1
            for line in _read(memory / store).splitlines()
            if line.strip().startswith("-")
        )
        counts.append(f"{store} {count} 条")
    return " / ".join(counts)


def memory_context(task_path: Path) -> str | None:
    if (
        task_path.name.lower() != TRIGGER
        or task_path.parent.name not in {RUNTIME_DIR, LEGACY_RUNTIME_DIR}
    ):
        return None
    memory = memory_dir(task_path.parent.parent)
    if not memory.is_dir():
        return (
            "## Memory\n\n本项目还没有 `.agent-loop/memory/`。"
            "**先按 `agent-memory` 建起来再往下做**"
            "——没有它，「这件事是不是已经做过」无从判断。"
        )

    index = _read(memory / "INDEX.md").strip()
    parts = ["## Memory（由 hook 注入，非可选）"]
    parts.append(index if index else "⚠️ `INDEX.md` 缺失或为空——索引坏了，不代表没有记忆。")

    line_count = len([line for line in index.splitlines() if line.strip()])
    if line_count > INDEX_MAX_LINES:
        parts.append(
            f"⚠️ **`INDEX.md` 已 {line_count} 行，超过 {INDEX_MAX_LINES} 行上限。** "
            "它是唯一常驻的一层，过长会被忽略中段、退化成没有索引。"
            "先把条目并粗（指向小节而不是逐条），再往下做。"
        )

    hits = _hits(_terms(_read(task_path)), memory)
    if hits:
        parts.append("### 与当前 task 词面相关\n" + "\n".join(f"- {hit}" for hit in hits))
    else:
        parts.append(
            f"### 无词面命中\n库存：{_health(memory)}。"
            "**命中为空不等于没做过**，按上面索引判断是否要定向细读。"
        )
    return "\n\n".join(parts)


def request_goal_review(roots: tuple[Path, ...]) -> int:
    count = 0
    for root in roots:
        try:
            request_pause(
                root,
                reason="goal_review_due: context compacted",
                kind="goal_review",
            )
            count += 1
        except HarnessError:
            pass
    return count


def handle(request: HookRequest) -> HookResponse:
    if request.event == HookEvent.TOOL_USED:
        task_path = _find_path(request.tool_input)
        if task_path and not task_path.is_absolute() and request.workspace_roots:
            task_path = request.workspace_roots[0] / task_path
        context = memory_context(task_path) if task_path else None
        if context:
            return HookResponse(HookAction.CONTEXT, context)
        return HookResponse()

    if request.event == HookEvent.COMPACT:
        request_goal_review(request.workspace_roots)
        return HookResponse()

    if request.event == HookEvent.STOP and request.status == "completed":
        messages = []
        for root in request.workspace_roots:
            try:
                message = completion_gate(root)
            except HarnessError as exc:
                message = f"Harness completion gate failed: {exc}"
            if message:
                messages.append(message)
        if messages:
            return HookResponse(HookAction.CONTINUE, "\n\n".join(messages))

    return HookResponse()
