from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import tests.context  # noqa: F401
from snowbreak_launcher.models import GitHubRelease, InstallInfo, LauncherState
from snowbreak_launcher.update_logic import decide_next_state


class UpdateLogicTests(unittest.TestCase):
    def _install(self) -> InstallInfo:
        root = Path(tempfile.gettempdir()) / "SnowbreakFake"
        return InstallInfo(
            install_type="Standalone",
            game_root=root,
            paks_root=root / "Game" / "Content" / "Paks",
            ix_folder=root / "Game" / "Content" / "Paks" / "~ix",
            localization_path=root / "Game" / "cbjq" / "localization.txt",
        )

    def _release(self, tag: str) -> GitHubRelease:
        return GitHubRelease(tag_name=tag, html_url="https://example.invalid", assets=())

    def test_first_install_when_no_install_detected(self) -> None:
        decision = decide_next_state(LauncherState(), None, None, False, False)
        self.assertEqual(decision.ui_state, "ready_to_install")
        self.assertEqual(decision.action_label, "Install")

    def test_installed_current_ready_to_launch(self) -> None:
        state = LauncherState(installed_release="AntiAmend-current")
        decision = decide_next_state(state, self._install(), self._release("AntiAmend-current"), True, True)
        self.assertEqual(decision.ui_state, "ready_to_launch")
        self.assertEqual(decision.action_label, "Launch")
        self.assertTrue(decision.local_install_complete)

    def test_installed_outdated_ready_to_update(self) -> None:
        state = LauncherState(installed_release="AntiAmend-old")
        decision = decide_next_state(state, self._install(), self._release("AntiAmend-new"), True, True)
        self.assertEqual(decision.ui_state, "ready_to_update")
        self.assertEqual(decision.action_label, "Update")
        self.assertTrue(decision.local_install_complete)

    def test_static_missing_ready_to_install(self) -> None:
        state = LauncherState(installed_release="AntiAmend-current")
        decision = decide_next_state(state, self._install(), self._release("AntiAmend-current"), True, False)
        self.assertEqual(decision.ui_state, "ready_to_install")
        self.assertEqual(decision.action_label, "Install")
        self.assertFalse(decision.local_install_complete)

    def test_saved_state_with_missing_core_files_ready_to_install(self) -> None:
        state = LauncherState(installed_release="AntiAmend-current")
        decision = decide_next_state(state, self._install(), self._release("AntiAmend-current"), False, True)
        self.assertEqual(decision.ui_state, "ready_to_install")
        self.assertEqual(decision.action_label, "Install")
        self.assertFalse(decision.local_install_complete)

    def test_auto_update_flag_is_only_active_for_updates(self) -> None:
        state = LauncherState(installed_release="AntiAmend-old", auto_update_enabled=True)
        decision = decide_next_state(state, self._install(), self._release("AntiAmend-new"), True, True)
        self.assertTrue(decision.should_auto_update)


if __name__ == "__main__":
    unittest.main()
