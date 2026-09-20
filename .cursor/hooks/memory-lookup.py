#!/usr/bin/env python3
"""Inject the memory index (and any lexical hits) when the agent reads task.md.

Wired to postToolUse/Read so the lookup is not the model's decision: reading
task.md is what SELECT does, and this fires on it unconditionally.

Silence is a failure mode here. A broken index and a genuinely empty one must
not look alike, so every path that reaches task.md returns *something* — see
`_health`.
"""

import json
import os
import re
import sys

TRIGGER = "task.md"
STORES = ("facts.md", "episodes.md", "lessons.md")
MAX_HITS = 5
# INDEX 是唯一常驻的那一层。内容文件长了只在 RETRIEVE 时付费，索引长了每轮都付，
# 而且超过这个长度模型会开始忽略中段——那时它和没有索引等价。
INDEX_MAX_LINES = 30
STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "有", "的", "了",
    "把", "在", "是", "和", "到", "个", "不", "要", "还", "会", "已", "做",
}


def _emit(context: str | None) -> None:
    sys.stdout.write(json.dumps({"additional_context": context} if context else {}))
    sys.exit(0)


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _find_path(payload) -> str:
    """Hook input shape varies by Cursor version; scan for anything path-like."""
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, str) and node.lower().endswith(".md"):
            return node
    return ""


def _project_root(task_path: str) -> str:
    """Walk up from task.md looking for .cursor/.

    Deliberately not cwd-relative: installed as a *user* hook the script runs
    from ~/.cursor/, so a relative .cursor/memory would resolve under the home
    directory and silently never match.
    """
    cur = os.path.dirname(os.path.abspath(task_path))
    while True:
        if os.path.isdir(os.path.join(cur, ".cursor")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return ""
        cur = parent


def _terms(task_md: str) -> set[str]:
    """Query = the Goal line plus the row currently marked doing."""
    lines = [
        ln for ln in task_md.splitlines()
        if "🔬" in ln or ln.startswith("## Goal") or ln.startswith("<一句话")
    ]
    goal_idx = next((i for i, ln in enumerate(task_md.splitlines()) if ln.startswith("## Goal")), -1)
    if goal_idx >= 0:
        lines.extend(task_md.splitlines()[goal_idx + 1:goal_idx + 3])
    words = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}", " ".join(lines))
    return {w.lower() for w in words if w.lower() not in STOPWORDS}


def _hits(terms: set[str], root: str) -> list[str]:
    scored = []
    for store in STORES:
        for ln in _read(os.path.join(root, store)).splitlines():
            stripped = ln.strip()
            if not stripped.startswith("-") or len(stripped) < 8:
                continue
            low = stripped.lower()
            score = sum(1 for t in terms if t in low)
            if score:
                scored.append((score, f"{store}: {stripped.lstrip('- ')}"))
    scored.sort(key=lambda p: -p[0])
    return [text for _, text in scored[:MAX_HITS]]


def _health(root: str) -> str:
    counts = []
    for store in STORES:
        body = _read(os.path.join(root, store))
        counts.append(f"{store} {sum(1 for ln in body.splitlines() if ln.strip().startswith('-'))} 条")
    return " / ".join(counts)


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        _emit(None)

    task_path = _find_path(payload)
    if os.path.basename(task_path).lower() != TRIGGER:
        _emit(None)

    project = _project_root(task_path)
    root = os.path.join(project, ".cursor", "memory") if project else ""
    if not root or not os.path.isdir(root):
        _emit(
            "## Memory\n\n本项目还没有 `.cursor/memory/`。**先按 `agent-memory` 建起来再往下做**"
            "——没有它，「这件事是不是已经做过」无从判断。"
        )

    index = _read(os.path.join(root, "INDEX.md")).strip()
    parts = ["## Memory（由 hook 注入，非可选）"]
    parts.append(index if index else "⚠️ `INDEX.md` 缺失或为空——索引坏了，不代表没有记忆。")

    n = len([ln for ln in index.splitlines() if ln.strip()])
    if n > INDEX_MAX_LINES:
        parts.append(
            f"⚠️ **`INDEX.md` 已 {n} 行，超过 {INDEX_MAX_LINES} 行上限。** 它是唯一常驻的一层，"
            "过长会被忽略中段、退化成没有索引。先把条目并粗（指向小节而不是逐条），再往下做。"
        )

    hits = _hits(_terms(_read(task_path)), root)
    if hits:
        parts.append("### 与当前 task 词面相关\n" + "\n".join(f"- {h}" for h in hits))
    else:
        parts.append(f"### 无词面命中\n库存：{_health(root)}。**命中为空不等于没做过**，按上面索引判断是否要定向细读。")

    _emit("\n\n".join(parts))


if __name__ == "__main__":
    main()
