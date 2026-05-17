from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tests.context  # noqa: F401
from snowbreak_launcher.models import InstallInfo
from snowbreak_launcher.permissions import (
    clear_readonly_for_launcher_path,
    install_requires_admin,
    is_path_in_protected_folder,
)


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

    def test_clears_readonly_inside_ix_folder_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ix = root / "Game" / "Content" / "Paks" / "~ix"
            ix.mkdir(parents=True)
            target = ix / "core.pak"
            target.write_text("pak", encoding="utf-8")
            target.chmod(0o444)

            clear_readonly_for_launcher_path(target, ix_folder=ix)

            self.assertTrue(target.stat().st_mode & 0o200)

    def test_refuses_to_clear_readonly_outside_owned_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ix = root / "Game" / "Content" / "Paks" / "~ix"
            ix.mkdir(parents=True)
            outside = root / "Game" / "Content" / "Paks" / "other.pak"
            outside.parent.mkdir(parents=True, exist_ok=True)
            outside.write_text("pak", encoding="utf-8")

            with self.assertRaises(ValueError):
                clear_readonly_for_launcher_path(outside, ix_folder=ix)

    def test_allows_exact_paks_root_without_recursing_into_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paks = Path(temp) / "Game" / "Content" / "Paks"
            paks.mkdir(parents=True)
            child = paks / "game-file.pak"
            child.write_text("pak", encoding="utf-8")
            paks.chmod(0o555)
            child.chmod(0o444)

            clear_readonly_for_launcher_path(paks, paks_root=paks)

            self.assertTrue(paks.stat().st_mode & 0o200)
            self.assertFalse(child.stat().st_mode & 0o200)

    def test_allows_exact_localization_parent_without_recursing_into_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp) / "Game" / "cbjq"
            parent.mkdir(parents=True)
            child = parent / "other.txt"
            child.write_text("keep", encoding="utf-8")
            parent.chmod(0o555)
            child.chmod(0o444)

            clear_readonly_for_launcher_path(parent, localization_parent=parent)

            self.assertTrue(parent.stat().st_mode & 0o200)
            self.assertFalse(child.stat().st_mode & 0o200)


if __name__ == "__main__":
    unittest.main()
