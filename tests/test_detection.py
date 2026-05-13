from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import tests.context  # noqa: F401
from snowbreak_launcher.constants import MANAGED_FOLDER_NAME
from snowbreak_launcher.detection import resolve_manual_install, validate_ix_folder


class DetectionTests(unittest.TestCase):
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

    def test_validate_ix_folder_rejects_non_paks_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(ValueError):
                validate_ix_folder(root / "NotPaks", root / "NotPaks" / MANAGED_FOLDER_NAME)


if __name__ == "__main__":
    unittest.main()
