from __future__ import annotations

import unittest

import tests.context  # noqa: F401
from snowbreak_launcher.config import clear_install_state
from snowbreak_launcher.models import LauncherState


class ConfigTests(unittest.TestCase):
    def test_clear_install_state_removes_paths_and_installed_metadata(self) -> None:
        state = LauncherState(
            accepted_notice=True,
            auto_update_enabled=True,
            install_type="Steam",
            game_root="C:/Games/SNOWBREAK",
            paks_root="C:/Games/SNOWBREAK/Game/Content/Paks",
            ix_folder="C:/Games/SNOWBREAK/Game/Content/Paks/~ix",
            localization_path="C:/Games/localization.txt",
            launcher_exe="C:/Games/Launcher.exe",
            last_checked_release="AntiAmend-current",
            last_check_time="2026-05-15T12:00:00",
            installed_release="AntiAmend-current",
            installed_files={"core.pak": "hash"},
            static_asset_pack={"sha256": "hash"},
        )

        clear_install_state(state)

        self.assertTrue(state.accepted_notice)
        self.assertTrue(state.auto_update_enabled)
        self.assertEqual(state.last_checked_release, "AntiAmend-current")
        self.assertEqual(state.last_check_time, "2026-05-15T12:00:00")
        self.assertIsNone(state.install_type)
        self.assertIsNone(state.game_root)
        self.assertIsNone(state.paks_root)
        self.assertIsNone(state.ix_folder)
        self.assertIsNone(state.localization_path)
        self.assertIsNone(state.launcher_exe)
        self.assertIsNone(state.installed_release)
        self.assertEqual(state.installed_files, {})
        self.assertEqual(state.static_asset_pack, {})


if __name__ == "__main__":
    unittest.main()
