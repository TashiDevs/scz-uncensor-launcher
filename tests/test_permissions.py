from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import tests.context  # noqa: F401
from snowbreak_launcher.models import InstallInfo
from snowbreak_launcher.permissions import install_requires_admin, is_path_in_protected_folder


class PermissionTests(unittest.TestCase):
    def _install(self, root: Path) -> InstallInfo:
        return InstallInfo(
            install_type="Standalone",
            game_root=root,
            paks_root=root / "Game" / "Content" / "Paks",
            ix_folder=root / "Game" / "Content" / "Paks" / "~ix",
            localization_path=root / "Game" / "cbjq" / "localization.txt",
        )

    def test_detects_path_under_program_files_as_protected(self) -> None:
        with patch.dict("os.environ", {"ProgramFiles": r"C:\Program Files"}, clear=True):
            self.assertTrue(is_path_in_protected_folder(Path(r"C:\Program Files\Snowbreak")))

    def test_does_not_treat_normal_game_folder_as_protected(self) -> None:
        with patch.dict("os.environ", {"ProgramFiles": r"C:\Program Files"}, clear=True):
            self.assertFalse(is_path_in_protected_folder(Path(r"D:\SeasunSnowBreakOs\Game\snowbreak")))

    def test_install_requires_admin_for_protected_install_when_not_elevated(self) -> None:
        install = self._install(Path(r"C:\Program Files\Snowbreak"))
        with (
            patch.dict("os.environ", {"ProgramFiles": r"C:\Program Files"}, clear=True),
            patch("snowbreak_launcher.permissions.is_running_as_admin", return_value=False),
        ):
            self.assertTrue(install_requires_admin(install))

    def test_install_does_not_require_admin_when_already_elevated(self) -> None:
        install = self._install(Path(r"C:\Program Files\Snowbreak"))
        with (
            patch.dict("os.environ", {"ProgramFiles": r"C:\Program Files"}, clear=True),
            patch("snowbreak_launcher.permissions.is_running_as_admin", return_value=True),
        ):
            self.assertFalse(install_requires_admin(install))


if __name__ == "__main__":
    unittest.main()
