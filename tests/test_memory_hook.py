from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

HOOK_PATH = (
    Path(__file__).resolve().parents[1]
    / "adapters"
    / "cursor"
    / "hooks"
    / "memory-lookup.py"
)
SPEC = importlib.util.spec_from_file_location("memory_lookup", HOOK_PATH)
assert SPEC and SPEC.loader
HOOK = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HOOK
SPEC.loader.exec_module(HOOK)


class MemoryHookTest(unittest.TestCase):
    def test_cursor_payload_is_decoded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / ".agent-loop"
            memory = runtime / "memory"
            memory.mkdir(parents=True)
            task = runtime / "task.md"
            task.write_text("## Goal\ncodec boundary\n", encoding="utf-8")
            (memory / "INDEX.md").write_text("- codec decision\n", encoding="utf-8")

            context = HOOK.context_for(
                {
                    "workspace_roots": [directory],
                    "tool_name": "Read",
                    "tool_input": {"path": str(task)},
                }
            )

        self.assertIn("codec decision", context or "")


if __name__ == "__main__":
    unittest.main()
