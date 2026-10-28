from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from harness.storage import atomic_write_json


class AtomicWriteTest(unittest.TestCase):
    def test_write_waits_for_a_brief_reader_and_fails_cleanly(self) -> None:
        with self.subTest("a reader holding the file briefly"):
            path = self.state({"phase": "ready"})
            opened = threading.Event()

            def read() -> None:
                with path.open(encoding="utf-8"):
                    opened.set()
                    time.sleep(0.2)

            reader = threading.Thread(target=read)
            reader.start()
            opened.wait(5)
            atomic_write_json(path, {"phase": "running"})
            reader.join()
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"phase": "running"})

        with self.subTest("retries exhausted"):
            path = self.state({"phase": "ready"})
            denied = PermissionError(13, "Access is denied")
            with (
                mock.patch("harness.storage.os.name", "nt"),
                mock.patch("harness.storage.os.replace", side_effect=denied),
                mock.patch("harness.storage.time.sleep"),
                mock.patch("pathlib.Path.unlink", side_effect=OSError("busy")),
            ):
                with self.assertRaises(PermissionError) as raised:
                    atomic_write_json(path, {"phase": "running"})
            self.assertIs(raised.exception, denied)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"phase": "ready"})
            with (
                mock.patch("harness.storage.os.name", "nt"),
                mock.patch("harness.storage.os.replace", side_effect=denied),
                mock.patch("harness.storage.time.sleep"),
                self.assertRaises(PermissionError),
            ):
                atomic_write_json(path, {"phase": "running"})
            self.assertEqual([p.name for p in path.parent.iterdir()], ["state.json"])

        for name, error in (("posix", PermissionError(13, "denied")), ("nt", OSError(28, "No space left"))):
            with self.subTest("no retry", os_name=name, error=type(error).__name__):
                path = self.state({"phase": "ready"})
                with (
                    mock.patch("harness.storage.os.name", name),
                    mock.patch("harness.storage.os.replace", side_effect=error) as replace,
                    mock.patch("harness.storage.time.sleep"),
                    self.assertRaises(type(error)),
                ):
                    atomic_write_json(path, {"phase": "running"})
                self.assertEqual(replace.call_count, 1)

    def state(self, value: dict[str, str]) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "state.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
