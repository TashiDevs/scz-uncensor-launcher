from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tests.context  # noqa: F401
from snowbreak_launcher.config import cleanup_app_data, load_state, save_state
from snowbreak_launcher.models import LauncherState


class ConfigStateTests(unittest.TestCase):
    def test_auto_update_state_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_file = Path(temp) / "state.json"
            with patch("snowbreak_launcher.config.state_path", return_value=state_file):
                save_state(LauncherState(auto_update_enabled=True, installed_release="AntiAmend-test"))
                loaded = load_state()

        self.assertTrue(loaded.auto_update_enabled)
        self.assertEqual(loaded.installed_release, "AntiAmend-test")

    def test_static_asset_pack_state_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_file = Path(temp) / "state.json"
            with patch("snowbreak_launcher.config.state_path", return_value=state_file):
                save_state(LauncherState(static_asset_pack={"url": "https://example.invalid/assets.zip", "sha256": "abc"}))
                loaded = load_state()

        self.assertEqual(loaded.static_asset_pack, {"url": "https://example.invalid/assets.zip", "sha256": "abc"})

    def test_load_state_defaults_missing_static_asset_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_file = Path(temp) / "state.json"
            state_file.write_text('{"installed_release": "AntiAmend-current"}', encoding="utf-8")
            with patch("snowbreak_launcher.config.state_path", return_value=state_file):
                loaded = load_state()

        self.assertEqual(loaded.static_asset_pack, {})

    def test_cleanup_app_data_keeps_only_settings_and_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("state.json", "launcher.log", "self-update.log"):
                (root / name).write_text("keep", encoding="utf-8")
            (root / "old.exe").write_text("remove", encoding="utf-8")
            (root / "leftover.download").write_text("remove", encoding="utf-8")
            downloads = root / "downloads"
            downloads.mkdir()
            (downloads / "cached.pak").write_text("remove", encoding="utf-8")
            updater = root / "updater"
            updater.mkdir()
            (updater / "helper.exe").write_text("remove", encoding="utf-8")

            with patch("snowbreak_launcher.config.app_data_dir", return_value=root):
                removed = cleanup_app_data()

            self.assertEqual({item.name for item in root.iterdir()}, {"state.json", "launcher.log", "self-update.log"})
            self.assertIn(downloads, removed)
            self.assertIn(updater, removed)


if __name__ == "__main__":
    unittest.main()
