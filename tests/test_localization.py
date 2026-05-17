from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tests.context  # noqa: F401
from snowbreak_launcher.localization import ensure_localization_enabled, is_localization_enabled


class LocalizationTests(unittest.TestCase):
    def test_missing_file_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "localization.txt"
            ensure_localization_enabled(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "localization = 1\n")
            self.assertTrue(is_localization_enabled(path))

    def test_parent_folder_is_made_writable_before_missing_file_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "Game" / "cbjq" / "localization.txt"
            path.parent.mkdir(parents=True)

            with patch("snowbreak_launcher.localization.clear_readonly_for_launcher_path") as clear_readonly:
                ensure_localization_enabled(path)

            clear_readonly.assert_any_call(path.parent, localization_parent=path.parent)

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

    def test_existing_file_is_made_writable_before_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "localization.txt"
            path.write_text("localization = 0\n", encoding="utf-8")
            with patch("snowbreak_launcher.localization.clear_readonly_for_launcher_path") as clear_readonly:
                ensure_localization_enabled(path)

            clear_readonly.assert_called_once_with(path, localization_path=path)


if __name__ == "__main__":
    unittest.main()
