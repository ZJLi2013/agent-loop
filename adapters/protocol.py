from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class HookEvent(str, Enum):
    TOOL_USED = "tool_used"
    COMPACT = "compact"
    STOP = "stop"


class HookAction(str, Enum):
    ALLOW = "allow"
    CONTEXT = "context"
    CONTINUE = "continue"


@dataclass(frozen=True)
class HookRequest:
    event: HookEvent
    workspace_roots: tuple[Path, ...]
    tool_name: str = ""
    tool_input: Any = None
    status: str = ""


@dataclass(frozen=True)
class HookResponse:
    action: HookAction = HookAction.ALLOW
    message: str | None = None
