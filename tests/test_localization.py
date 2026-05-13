from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import tests.context  # noqa: F401
from snowbreak_launcher.localization import ensure_localization_enabled, is_localization_enabled


class LocalizationTests(unittest.TestCase):
    def test_missing_file_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "localization.txt"
            ensure_localization_enabled(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "localization = 1\n")
            self.assertTrue(is_localization_enabled(path))

    def test_numeric_switch_is_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "localization.txt"
            path.write_text("0", encoding="utf-8")
            ensure_localization_enabled(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "localization = 1\n")

    def test_existing_assignment_is_updated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "localization.txt"
            path.write_text("localization = 0\n", encoding="utf-8")
            ensure_localization_enabled(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "localization = 1\n")


if __name__ == "__main__":
    unittest.main()
