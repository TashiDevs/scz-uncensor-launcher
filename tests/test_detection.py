from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tests.context  # noqa: F401
from snowbreak_launcher.constants import MANAGED_FOLDER_NAME
from snowbreak_launcher.detection import _detect_standalone_installs, build_install_info, resolve_manual_install, validate_ix_folder


class DetectionTests(unittest.TestCase):
    def _make_seasun_nested_install(self, temp: str) -> tuple[Path, Path, Path]:
        base = Path(temp) / "SeasunSnowBreakOs"
        game = base / "Game" / "snowbreak"
        paks = game / "Game" / "Content" / "Paks"
        paks.mkdir(parents=True)
        (base / "launcher.exe").write_text("", encoding="utf-8")
        return base, game, paks

    def test_steam_root_sets_localization_in_common_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            common = Path(temp) / "SteamLibrary" / "steamapps" / "common"
            game = common / "SNOWBREAK"
            paks = game / "Game" / "Content" / "Paks"
            paks.mkdir(parents=True)

            install = resolve_manual_install(game)

            self.assertIsNotNone(install)
            assert install is not None
            self.assertEqual(install.install_type, "Steam")
            self.assertEqual(install.localization_path, common / "localization.txt")
            self.assertEqual(install.ix_folder, paks / MANAGED_FOLDER_NAME)

    def test_steam_paks_folder_still_detects_steam(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            common = Path(temp) / "SteamLibrary" / "steamapps" / "common"
            game = common / "SNOWBREAK"
            paks = game / "Game" / "Content" / "Paks"
            paks.mkdir(parents=True)

            install = resolve_manual_install(paks)

            self.assertIsNotNone(install)
            assert install is not None
            self.assertEqual(install.install_type, "Steam")
            self.assertEqual(install.localization_path, common / "localization.txt")

    def test_standalone_prefers_game_cbjq_localization_when_parent_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Snowbreak"
            (root / "Game" / "Content" / "Paks").mkdir(parents=True)
            (root / "Game" / "cbjq").mkdir(parents=True)

            install = resolve_manual_install(root)

            self.assertIsNotNone(install)
            assert install is not None
            self.assertEqual(install.install_type, "Standalone")
            self.assertEqual(install.localization_path, root / "Game" / "cbjq" / "localization.txt")

    def test_seasun_registry_game_path_detects_nested_standalone_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base, game, paks = self._make_seasun_nested_install(temp)

            with (
                patch("snowbreak_launcher.detection._seasun_standalone_registry_locations", return_value=[game]),
                patch("snowbreak_launcher.detection._standalone_registry_locations", return_value=[]),
            ):
                installs = _detect_standalone_installs()

            self.assertTrue(installs)
            install = installs[0]
            self.assertEqual(install.install_type, "Standalone")
            self.assertEqual(install.game_root, game.resolve())
            self.assertEqual(install.paks_root, paks.resolve())
            self.assertEqual(install.launcher_exe, base / "launcher.exe")

    def test_manual_picker_accepts_seasun_base_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base, game, paks = self._make_seasun_nested_install(temp)

            install = resolve_manual_install(base)

            self.assertIsNotNone(install)
            assert install is not None
            self.assertEqual(install.install_type, "Standalone")
            self.assertEqual(install.game_root, game.resolve())
            self.assertEqual(install.paks_root, paks.resolve())

    def test_manual_picker_accepts_seasun_nested_game_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base, game, _paks = self._make_seasun_nested_install(temp)

            install = resolve_manual_install(game)

            self.assertIsNotNone(install)
            assert install is not None
            self.assertEqual(install.game_root, game.resolve())
            self.assertEqual(install.launcher_exe, base / "launcher.exe")

    def test_standalone_launcher_can_live_in_seasun_base_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base, game, _paks = self._make_seasun_nested_install(temp)

            install = build_install_info(game, install_type="Standalone")

            self.assertIsNotNone(install)
            assert install is not None
            self.assertEqual(install.launcher_exe, base / "launcher.exe")

    def test_invalid_seasun_registry_path_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "SeasunSnowBreakOs" / "Game" / "snowbreak"

            with (
                patch("snowbreak_launcher.detection._seasun_standalone_registry_locations", return_value=[missing]),
                patch("snowbreak_launcher.detection._standalone_registry_locations", return_value=[]),
            ):
                installs = _detect_standalone_installs()

            self.assertEqual(installs, [])

    def test_validate_ix_folder_rejects_non_paks_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(ValueError):
                validate_ix_folder(root / "NotPaks", root / "NotPaks" / MANAGED_FOLDER_NAME)


if __name__ == "__main__":
    unittest.main()
