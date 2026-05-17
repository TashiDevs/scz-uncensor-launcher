from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tests.context  # noqa: F401
from snowbreak_launcher.constants import APP_VERSION
from snowbreak_launcher.models import GitHubAsset, GitHubRelease, InstallInfo, LauncherState
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
                    "write_blocked",
                    "ready_to_launch",
                    "error",
                ):
                    app.ui_state = state
                    app._render()
                    qt_app.processEvents()
            finally:
                app.close()
                app.deleteLater()

    def test_write_blocked_state_shows_retry_and_open_ix(self) -> None:
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
                app._last_action = "setup"
                app._show_error("Snowbreak files are read-only or locked.", kind="write_blocked")
                qt_app.processEvents()

                self.assertEqual(app.ui_state, "write_blocked")
                self.assertEqual(app.top_title, "Folder blocked")
                self.assertEqual(app.top_detail, "Snowbreak files are read-only or locked.")
                self.assertEqual(app.status_label._text, "Fix the folder, then retry.")
                self.assertEqual(app.main_button.text(), "Retry")
                self.assertTrue(app.grant_admin_button.isHidden())
                self.assertFalse(app.open_ix_button.isHidden())
            finally:
                app.close()
                app.deleteLater()

    def test_write_blocked_retry_repeats_setup_action(self) -> None:
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
            app.ui_state = "write_blocked"
            with patch.object(app, "_start_setup_or_update") as start_setup:
                app._main_action()
            start_setup.assert_called_once()
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

    def test_setup_permission_error_classification_uses_write_blocked_when_admin_would_not_help(self) -> None:
        from snowbreak_launcher.app import _setup_error_kind

        with tempfile.TemporaryDirectory() as temp:
            install = self._make_install(temp)
            with patch("snowbreak_launcher.app.install_requires_admin", return_value=False):
                self.assertEqual(_setup_error_kind(PermissionError("read only"), install), "write_blocked")

    def test_setup_permission_error_classification_keeps_admin_for_protected_unelevated_install(self) -> None:
        from snowbreak_launcher.app import _setup_error_kind

        with tempfile.TemporaryDirectory() as temp:
            install = self._make_install(temp)
            with patch("snowbreak_launcher.app.install_requires_admin", return_value=True):
                self.assertEqual(_setup_error_kind(PermissionError("protected"), install), "permission")

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
                self.assertEqual(app.chips["Mods"]._text, "No other mods")
                self.assertNotIn("Assets", app.chips)
                self.assertTrue(app.uninstall_button.isHidden())
                self.assertTrue(app.auto_update_pill.isHidden())
            finally:
                app.close()
                app.deleteLater()

    def test_uninstall_clears_saved_install_choice(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QMessageBox
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with tempfile.TemporaryDirectory() as temp:
            install = self._make_install(temp)
            state = LauncherState(
                accepted_notice=True,
                auto_update_enabled=True,
                install_type="Steam",
                game_root=str(install.game_root),
                paks_root=str(install.paks_root),
                ix_folder=str(install.ix_folder),
                localization_path=str(install.localization_path),
                installed_release="AntiAmend-current",
                installed_files={"core.pak": "hash"},
                static_asset_pack={"sha256": "hash"},
            )

            with (
                patch("snowbreak_launcher.app.load_state", return_value=state),
                patch("snowbreak_launcher.app.cleanup_app_data"),
            ):
                qt_app = create_application([])
                app = SnowbreakLauncherApp()
            try:
                app.install = install
                app.local_install_complete = True
                with (
                    patch("snowbreak_launcher.app.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes) as question,
                    patch("snowbreak_launcher.app.uninstall_all_managed_files", return_value=0),
                ):
                    app._uninstall()
                qt_app.processEvents()

                self.assertNotIn("Nothing outside ~ix will be touched.", question.call_args.args[2])
                self.assertIsNone(app.install)
                self.assertIsNone(app.state_data.game_root)
                self.assertIsNone(app.state_data.installed_release)
                self.assertEqual(app.state_data.installed_files, {})
                self.assertEqual(app.state_data.static_asset_pack, {})
                self.assertTrue(app.state_data.accepted_notice)
                self.assertTrue(app.state_data.auto_update_enabled)
                self.assertTrue(app.uninstall_button.isHidden())
                self.assertEqual(app.main_button.text(), "Choose Folder")
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

    def test_multiple_detected_installs_render_choose_install(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with tempfile.TemporaryDirectory() as temp:
            steam_install = self._make_install(str(Path(temp) / "Steam"))
            standalone_install = InstallInfo(
                install_type="Standalone",
                game_root=Path(temp) / "Standalone",
                paks_root=Path(temp) / "Standalone" / "Game" / "Content" / "Paks",
                ix_folder=Path(temp) / "Standalone" / "Game" / "Content" / "Paks" / "~ix",
                localization_path=Path(temp) / "Standalone" / "Game" / "cbjq" / "localization.txt",
            )
            standalone_install.ix_folder.mkdir(parents=True)
            standalone_install.localization_path.parent.mkdir(parents=True)

            with (
                patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)),
                patch("snowbreak_launcher.app.cleanup_app_data"),
            ):
                qt_app = create_application([])
                app = SnowbreakLauncherApp()
            try:
                app._finish_checks(None, None, None, [steam_install, standalone_install])
                qt_app.processEvents()

                self.assertEqual(app.ui_state, "choose_install")
                self.assertEqual(app.top_title, "Choose install")
                self.assertEqual(app.main_button.text(), "Choose Install")
                self.assertEqual(app.status_label._text, "Choose which Snowbreak install to manage.")
            finally:
                app.close()
                app.deleteLater()

    def test_choose_detected_install_saves_selected_choice(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, _install_choice_label, create_application

        with tempfile.TemporaryDirectory() as temp:
            first_install = self._make_install(str(Path(temp) / "First"))
            second_install = self._make_install(str(Path(temp) / "Second"))
            second_install = InstallInfo(
                install_type="Standalone",
                game_root=second_install.game_root,
                paks_root=second_install.paks_root,
                ix_folder=second_install.ix_folder,
                localization_path=second_install.localization_path,
            )

            with (
                patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)),
                patch("snowbreak_launcher.app.cleanup_app_data"),
            ):
                qt_app = create_application([])
                app = SnowbreakLauncherApp()
            try:
                app.detected_install_choices = [first_install, second_install]
                chosen_label = _install_choice_label(second_install)

                with (
                    patch("snowbreak_launcher.app.QInputDialog.getItem", return_value=(chosen_label, True)),
                    patch.object(app, "_start_checks") as start_checks,
                ):
                    self.assertTrue(app._choose_detected_install())

                self.assertEqual(app.install, second_install)
                self.assertEqual(app.state_data.install_type, "Standalone")
                self.assertEqual(app.state_data.game_root, str(second_install.game_root))
                start_checks.assert_called_once()
            finally:
                app.close()
                app.deleteLater()

    def test_manual_picker_uses_snowbreak_installation_folder_title(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with (
            patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)),
            patch("snowbreak_launcher.app.cleanup_app_data"),
        ):
            qt_app = create_application([])
            app = SnowbreakLauncherApp()
        try:
            with patch("snowbreak_launcher.app.QFileDialog.getExistingDirectory", return_value="") as picker:
                self.assertFalse(app._choose_folder())

            picker.assert_called_once()
            self.assertEqual(picker.call_args.args[1], "Choose Snowbreak installation folder")
        finally:
            app.close()
            app.deleteLater()

    def test_complete_install_with_new_release_renders_as_update(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with tempfile.TemporaryDirectory() as temp:
            install = self._make_install(temp)
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
                self.assertEqual(app.chips["Mods"]._text, "No other mods")
                self.assertNotIn("Assets", app.chips)
                self.assertFalse(app.uninstall_button.isHidden())
                self.assertFalse(app.auto_update_pill.isHidden())
            finally:
                app.close()
                app.deleteLater()

    def test_current_install_with_obsolete_ix_files_renders_as_update_cleanup(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with tempfile.TemporaryDirectory() as temp:
            install = self._make_install(temp)
            (install.ix_folder / "core.pak").write_text("core-current", encoding="utf-8")
            (install.ix_folder / "character-anti-censorship_99_P.pak").write_text("old static", encoding="utf-8")
            state = LauncherState(
                accepted_notice=True,
                installed_release="AntiAmend-current",
                installed_files={"core.pak": _sha("core-current")},
            )
            release = GitHubRelease(
                "AntiAmend-current",
                "https://example.invalid",
                assets=(GitHubAsset("core.pak", 12, _sha("core-current"), "https://example.invalid/core.pak"),),
            )

            with (
                patch("snowbreak_launcher.app.load_state", return_value=state),
                patch("snowbreak_launcher.app.cleanup_app_data"),
            ):
                qt_app = create_application([])
                app = SnowbreakLauncherApp()
            try:
                app._finish_checks(install, release)
                qt_app.processEvents()

                self.assertEqual(app.ui_state, "ready_to_update")
                self.assertEqual(app.main_button.text(), "Update")
                self.assertEqual(app.status_label._text, "Cleanup needed.")
                self.assertEqual(app.chips["Core"]._text, "Cleanup needed")
            finally:
                app.close()
                app.deleteLater()

    def test_mod_folder_warning_shows_for_first_install(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with tempfile.TemporaryDirectory() as temp:
            install = self._make_install(temp)
            (install.paks_root / "OldUncensor").mkdir()

            with (
                patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)),
                patch("snowbreak_launcher.app.cleanup_app_data"),
            ):
                qt_app = create_application([])
                app = SnowbreakLauncherApp()
            try:
                app._finish_checks(install, GitHubRelease("AntiAmend-current", "https://example.invalid", assets=()))
                qt_app.processEvents()

                self.assertEqual(app.ui_state, "ready_to_install")
                self.assertEqual(app.chips["Mods"]._text, "Other mods installed")
                self.assertEqual(app.status_label._text, "Make sure there are no conflicting mods.")
            finally:
                app.close()
                app.deleteLater()

    def test_static_asset_controls_are_removed_from_ui(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application

        with (
            patch("snowbreak_launcher.app.load_state", return_value=LauncherState(accepted_notice=True)),
            patch("snowbreak_launcher.app.cleanup_app_data"),
        ):
            qt_app = create_application([])
            app = SnowbreakLauncherApp()
        try:
            self.assertNotIn("Assets", app.chips)
            self.assertIn("Mods", app.chips)
            self.assertFalse(hasattr(app, "import_button"))
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

            self.assertEqual(app._watermark_text(), f"by Tashi - v{APP_VERSION}")
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
