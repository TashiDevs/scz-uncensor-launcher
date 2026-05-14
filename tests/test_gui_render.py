from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tests.context  # noqa: F401
from snowbreak_launcher.constants import STATIC_ASSET_NAMES
from snowbreak_launcher.models import GitHubRelease, InstallInfo, LauncherState
from snowbreak_launcher.self_update import LauncherUpdateInfo
from snowbreak_launcher.update_logic import UpdateDecision


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class GuiRenderTests(unittest.TestCase):
    def _make_install(self, temp: str) -> InstallInfo:
        root = Path(temp) / "Snowbreak"
        ix = root / "Game" / "Content" / "Paks" / "~ix"
        ix.mkdir(parents=True)
        localization = root / "Game" / "cbjq" / "localization.txt"
        localization.parent.mkdir(parents=True)
        localization.write_text("localization = 1\n", encoding="utf-8")
        return InstallInfo(
            install_type="Steam",
            game_root=root,
            paks_root=ix.parent,
            ix_folder=ix,
            localization_path=localization,
        )

    def test_render_core_states(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Snowbreak"
            ix = root / "Game" / "Content" / "Paks" / "~ix"
            ix.mkdir(parents=True)
            for name in STATIC_ASSET_NAMES:
                (ix / name).write_text("static", encoding="utf-8")
            localization = root / "Game" / "cbjq" / "localization.txt"
            localization.parent.mkdir(parents=True)
            localization.write_text("localization = 1\n", encoding="utf-8")

            install = InstallInfo(
                install_type="Standalone",
                game_root=root,
                paks_root=ix.parent,
                ix_folder=ix,
                localization_path=localization,
            )

            with patch("snowbreak_launcher.app.load_state", return_value=LauncherState()):
                qt_app = create_application([])
                app = SnowbreakLauncherApp()
            try:
                qt_app.processEvents()
                app.install = install
                app.state_data.installed_release = "AntiAmend-current"
                app.decision = UpdateDecision("ready_to_launch", "Launch", "Done.")

                for state in (
                    "disclaimer",
                    "checking",
                    "ready_to_install",
                    "ready_to_update",
                    "installing",
                    "updating",
                    "ready_to_launch",
                    "error",
                ):
                    app.ui_state = state
                    app._render()
                    qt_app.processEvents()
            finally:
                app.close()
                app.deleteLater()

    def test_incomplete_saved_install_renders_as_install(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with tempfile.TemporaryDirectory() as temp:
            install = self._make_install(temp)
            state = LauncherState(
                accepted_notice=True,
                installed_release="AntiAmend-current",
                installed_files={"core.pak": "hash"},
            )

            with patch("snowbreak_launcher.app.load_state", return_value=state):
                qt_app = create_application([])
                app = SnowbreakLauncherApp()
            try:
                app._finish_checks(install, GitHubRelease("AntiAmend-current", "https://example.invalid", assets=()))
                qt_app.processEvents()

                self.assertEqual(app.ui_state, "ready_to_install")
                self.assertEqual(app.top_title, "Setup needed")
                self.assertEqual(app.main_button.text(), "Install")
                self.assertEqual(app.chips["Game"]._text, "Steam found")
                self.assertEqual(app.chips["Switch"]._text, "loc=1")
                self.assertEqual(app.chips["Core"]._text, "Uncensor missing")
                self.assertEqual(app.chips["Assets"]._text, "Assets missing")
                self.assertTrue(app.uninstall_button.isHidden())
                self.assertTrue(app.auto_update_pill.isHidden())
            finally:
                app.close()
                app.deleteLater()

    def test_missing_game_renders_choose_folder_button(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)):
            qt_app = create_application([])
            app = SnowbreakLauncherApp()
        try:
            app._finish_checks(None, None)
            qt_app.processEvents()

            self.assertEqual(app.ui_state, "ready_to_install")
            self.assertEqual(app.top_title, "Game needed")
            self.assertEqual(app.main_button.text(), "Choose Folder")
        finally:
            app.close()
            app.deleteLater()

    def test_complete_install_with_new_release_renders_as_update(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with tempfile.TemporaryDirectory() as temp:
            install = self._make_install(temp)
            for name in STATIC_ASSET_NAMES:
                (install.ix_folder / name).write_text("static", encoding="utf-8")
            (install.ix_folder / "core.pak").write_text("core", encoding="utf-8")
            state = LauncherState(
                accepted_notice=True,
                installed_release="AntiAmend-old",
                installed_files={"core.pak": _sha("core")},
            )

            with patch("snowbreak_launcher.app.load_state", return_value=state):
                qt_app = create_application([])
                app = SnowbreakLauncherApp()
            try:
                app._finish_checks(install, GitHubRelease("AntiAmend-new", "https://example.invalid", assets=()))
                qt_app.processEvents()

                self.assertEqual(app.ui_state, "ready_to_update")
                self.assertEqual(app.top_title, "Update ready")
                self.assertEqual(app.main_button.text(), "Update")
                self.assertEqual(app.chips["Core"]._text, "Update available")
                self.assertEqual(app.chips["Assets"]._text, "Assets installed")
                self.assertFalse(app.uninstall_button.isHidden())
                self.assertFalse(app.auto_update_pill.isHidden())
            finally:
                app.close()
                app.deleteLater()

    def test_launch_closes_window_after_command(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with tempfile.TemporaryDirectory() as temp:
            install = self._make_install(temp)
            with patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)):
                qt_app = create_application([])
                app = SnowbreakLauncherApp()
            try:
                app.install = install
                app.show()
                qt_app.processEvents()
                with patch("snowbreak_launcher.app.launch_game") as fake_launch:
                    app._launch_game()
                fake_launch.assert_called_once()
                self.assertTrue(app.isHidden())
            finally:
                app.close()
                app.deleteLater()

    def test_asset_path_uses_pyinstaller_bundle_root(self) -> None:
        import snowbreak_launcher.app as launcher_app

        with tempfile.TemporaryDirectory() as temp:
            with patch.object(launcher_app.sys, "_MEIPASS", temp, create=True):
                self.assertEqual(launcher_app._asset_path("images", "background.png"), Path(temp) / "assets" / "images" / "background.png")

    def test_footer_includes_app_version_and_launcher_update_button(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)):
            qt_app = create_application([])
            app = SnowbreakLauncherApp()
        try:
            app.launcher_update = LauncherUpdateInfo(
                tag_name="v1.04",
                html_url="https://example.invalid/release",
                asset_name="SnowbreakUncensorLauncher.exe",
                asset_size=123,
                asset_sha256="a" * 64,
                download_url="https://example.invalid/SnowbreakUncensorLauncher.exe",
            )
            app.ui_state = "ready_to_install"
            app._render()
            qt_app.processEvents()

            self.assertEqual(app._watermark_text(), "by Tashi - v1.04")
            self.assertFalse(app.self_update_button.isHidden())
        finally:
            app.close()
            app.deleteLater()


if __name__ == "__main__":
    unittest.main()
