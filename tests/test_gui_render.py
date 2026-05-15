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

            with (
                patch("snowbreak_launcher.app.load_state", return_value=LauncherState()),
                patch("snowbreak_launcher.app.cleanup_app_data"),
            ):
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
                    "admin_needed",
                    "ready_to_launch",
                    "error",
                ):
                    app.ui_state = state
                    app._render()
                    qt_app.processEvents()
            finally:
                app.close()
                app.deleteLater()

    def test_admin_needed_state_shows_cancel_and_grant_admin(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with (
            patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)),
            patch("snowbreak_launcher.app.cleanup_app_data"),
        ):
            qt_app = create_application([])
            app = SnowbreakLauncherApp()
        try:
            app._show_admin_needed("Snowbreak is in a protected folder.")
            qt_app.processEvents()

            self.assertEqual(app.ui_state, "admin_needed")
            self.assertEqual(app.top_title, "Admin needed")
            self.assertEqual(app.main_button.text(), "Cancel")
            self.assertEqual(app.status_label._text, "Move the game install, or grant admin for this patch.")
            self.assertFalse(app.grant_admin_button.isHidden())
        finally:
            app.close()
            app.deleteLater()

    def test_retryable_error_uses_retry_button_and_repeats_setup_action(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with (
            patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)),
            patch("snowbreak_launcher.app.cleanup_app_data"),
        ):
            qt_app = create_application([])
            app = SnowbreakLauncherApp()
        try:
            app._last_action = "setup"
            app._show_error("Download failed. Check your connection and retry.", kind="network_retry")
            qt_app.processEvents()

            self.assertEqual(app.ui_state, "error")
            self.assertEqual(app.main_button.text(), "Retry")
            self.assertEqual(app.status_label._text, "Download failed. Check your connection and retry.")
            with patch.object(app, "_start_setup_or_update") as start_setup:
                app._main_action()
            start_setup.assert_called_once()
        finally:
            app.close()
            app.deleteLater()

    def test_start_setup_shows_admin_needed_for_protected_install(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with tempfile.TemporaryDirectory() as temp:
            install = self._make_install(temp)
            with (
                patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)),
                patch("snowbreak_launcher.app.cleanup_app_data"),
            ):
                qt_app = create_application([])
                app = SnowbreakLauncherApp()
            try:
                app.install = install
                with (
                    patch("snowbreak_launcher.app.install_requires_admin", return_value=True),
                    patch.object(app, "_run_worker") as run_worker,
                ):
                    app._start_setup_or_update()

                self.assertEqual(app.ui_state, "admin_needed")
                self.assertEqual(app.main_button.text(), "Cancel")
                run_worker.assert_not_called()
            finally:
                app.close()
                app.deleteLater()

    def test_cancel_button_uses_short_status_text(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with (
            patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)),
            patch("snowbreak_launcher.app.cleanup_app_data"),
        ):
            qt_app = create_application([])
            app = SnowbreakLauncherApp()
        try:
            app.busy = True
            app._cancel_action()
            qt_app.processEvents()

            self.assertTrue(app.cancel_requested)
            self.assertEqual(app.status_label._text, "Cancelling...")
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

            with (
                patch("snowbreak_launcher.app.load_state", return_value=state),
                patch("snowbreak_launcher.app.cleanup_app_data"),
            ):
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

        with (
            patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)),
            patch("snowbreak_launcher.app.cleanup_app_data"),
        ):
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

            with (
                patch("snowbreak_launcher.app.load_state", return_value=state),
                patch("snowbreak_launcher.app.cleanup_app_data"),
            ):
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
            with (
                patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)),
                patch("snowbreak_launcher.app.cleanup_app_data"),
            ):
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

    def test_launcher_update_uses_main_button_and_no_footer_button(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with (
            patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)),
            patch("snowbreak_launcher.app.cleanup_app_data"),
        ):
            qt_app = create_application([])
            app = SnowbreakLauncherApp()
        try:
            app.launcher_update = LauncherUpdateInfo(
                tag_name="v1.06",
                html_url="https://example.invalid/release",
                asset_name="SnowbreakUncensorLauncher.exe",
                asset_size=123,
                asset_sha256="a" * 64,
                download_url="https://example.invalid/SnowbreakUncensorLauncher.exe",
            )
            app.ui_state = "ready_to_install"
            app._render()
            qt_app.processEvents()

            self.assertEqual(app._watermark_text(), "by Tashi - v1.06")
            self.assertEqual(app.top_title, "Launcher update ready")
            self.assertEqual(app.main_button.text(), "Update Launcher")
            self.assertEqual(app.status_label._text, "Launcher update available: v1.06")
            self.assertFalse(hasattr(app, "self_update_button"))
            self.assertEqual(app.skip_update_button.text(), "Skip")
            self.assertFalse(app.skip_update_button.isHidden())
        finally:
            app.close()
            app.deleteLater()

    def test_auto_update_pill_uses_short_centered_label(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import AutoUpdatePill, create_application
        from PySide6.QtCore import Qt

        qt_app = create_application([])
        pill = AutoUpdatePill()
        try:
            qt_app.processEvents()

            self.assertEqual(pill.label_text, "Auto-update next time?")
            self.assertTrue(pill.label_alignment & Qt.AlignmentFlag.AlignHCenter)
        finally:
            pill.deleteLater()

    def test_main_action_starts_launcher_update_when_available(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with (
            patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)),
            patch("snowbreak_launcher.app.cleanup_app_data"),
        ):
            qt_app = create_application([])
            app = SnowbreakLauncherApp()
        try:
            app.launcher_update = LauncherUpdateInfo(
                tag_name="v1.06",
                html_url="https://example.invalid/release",
                asset_name="SnowbreakUncensorLauncher.exe",
                asset_size=123,
                asset_sha256="a" * 64,
                download_url="https://example.invalid/SnowbreakUncensorLauncher.exe",
            )
            app.ui_state = "ready_to_launch"
            app._render()
            qt_app.processEvents()

            with patch.object(app, "_start_launcher_self_update") as start_self_update:
                app._main_action()

            start_self_update.assert_called_once()
        finally:
            app.close()
            app.deleteLater()

    def test_skip_launcher_update_restores_normal_action(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with (
            patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)),
            patch("snowbreak_launcher.app.cleanup_app_data"),
        ):
            qt_app = create_application([])
            app = SnowbreakLauncherApp()
        try:
            app.launcher_update = LauncherUpdateInfo(
                tag_name="v1.07",
                html_url="https://example.invalid/release",
                asset_name="SnowbreakUncensorLauncher.exe",
                asset_size=123,
                asset_sha256="a" * 64,
                download_url="https://example.invalid/SnowbreakUncensorLauncher.exe",
            )
            app.ui_state = "ready_to_launch"
            app._render()
            self.assertEqual(app.main_button.text(), "Update Launcher")

            app._skip_launcher_update()
            qt_app.processEvents()

            self.assertFalse(app._launcher_update_has_priority())
            self.assertEqual(app.main_button.text(), "Launch")
            self.assertTrue(app.skip_update_button.isHidden())
        finally:
            app.close()
            app.deleteLater()

    def test_launcher_update_starts_without_confirmation_popup(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with (
            patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)),
            patch("snowbreak_launcher.app.cleanup_app_data"),
        ):
            qt_app = create_application([])
            app = SnowbreakLauncherApp()
        try:
            app.launcher_update = LauncherUpdateInfo(
                tag_name="v1.07",
                html_url="https://example.invalid/release",
                asset_name="SnowbreakUncensorLauncher.exe",
                asset_size=123,
                asset_sha256="a" * 64,
                download_url="https://example.invalid/SnowbreakUncensorLauncher.exe",
            )

            with (
                patch("snowbreak_launcher.app.is_packaged_app", return_value=True),
                patch("snowbreak_launcher.app.QMessageBox.question") as question,
                patch.object(app, "_run_worker") as run_worker,
            ):
                app._start_launcher_self_update()

            question.assert_not_called()
            run_worker.assert_called_once()
            self.assertEqual(app.ui_state, "self_updating")
        finally:
            app.close()
            app.deleteLater()


if __name__ == "__main__":
    unittest.main()
