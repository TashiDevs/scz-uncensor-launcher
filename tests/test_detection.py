from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tests.context  # noqa: F401
from snowbreak_launcher.constants import MANAGED_FOLDER_NAME
from snowbreak_launcher.detection import (
    SEASUN_STANDALONE_REGISTRY_FALLBACK_KEY,
    SEASUN_STANDALONE_REGISTRY_KEY,
    _detect_standalone_installs,
    _seasun_standalone_registry_locations,
    build_install_info,
    resolve_manual_install,
    validate_ix_folder,
)


class DetectionTests(unittest.TestCase):
    def _make_seasun_nested_install(self, temp: str) -> tuple[Path, Path, Path]:
        base = Path(temp) / "SeasunSnowBreakOs"
        game = base / "Game" / "snowbreak"
        paks = game / "Game" / "Content" / "Paks"
        paks.mkdir(parents=True)
        (base / "launcher.exe").write_text("", encoding="utf-8")
        return base, game, paks

    def _make_seasun_double_game_install(self, temp: str) -> tuple[Path, Path, Path, Path]:
        base = Path(temp) / "SeasunSnowBreakOs"
        game = base / "Game" / "snowbreak"
        nested_game = game / "game"
        paks = nested_game / "Game" / "Content" / "Paks"
        paks.mkdir(parents=True)
        (nested_game / "Game" / "cbjq").mkdir(parents=True)
        (base / "launcher.exe").write_text("", encoding="utf-8")
        return base, game, nested_game, paks

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

    def test_seasun_registry_reads_instpath_value_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _base, game, _paks = self._make_seasun_nested_install(temp)
            fake_winreg = _FakeWinreg({SEASUN_STANDALONE_REGISTRY_KEY: {"InstPath": str(game)}})

            with (
                patch("snowbreak_launcher.detection.os.name", "nt"),
                patch.dict(sys.modules, {"winreg": fake_winreg}),
            ):
                locations = _seasun_standalone_registry_locations()

            self.assertEqual(locations, [game])

    def test_seasun_registry_reads_older_instpath_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _base, game, _paks = self._make_seasun_nested_install(temp)
            fake_winreg = _FakeWinreg({SEASUN_STANDALONE_REGISTRY_FALLBACK_KEY: {"": str(game)}})

            with (
                patch("snowbreak_launcher.detection.os.name", "nt"),
                patch.dict(sys.modules, {"winreg": fake_winreg}),
            ):
                locations = _seasun_standalone_registry_locations()

            self.assertEqual(locations, [game])

    def test_seasun_registry_detects_double_game_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base, game, nested_game, paks = self._make_seasun_double_game_install(temp)

            with (
                patch("snowbreak_launcher.detection._seasun_standalone_registry_locations", return_value=[game]),
                patch("snowbreak_launcher.detection._standalone_registry_locations", return_value=[]),
            ):
                installs = _detect_standalone_installs()

            self.assertTrue(installs)
            install = installs[0]
            self.assertEqual(install.game_root, game.resolve())
            self.assertEqual(install.paks_root, paks.resolve())
            self.assertEqual(install.localization_path, nested_game / "Game" / "cbjq" / "localization.txt")
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

    def test_manual_picker_accepts_seasun_base_folder_with_double_game_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base, game, _nested_game, paks = self._make_seasun_double_game_install(temp)

            install = resolve_manual_install(base)

            self.assertIsNotNone(install)
            assert install is not None
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

    def test_manual_picker_accepts_double_game_intermediate_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base, _game, nested_game, paks = self._make_seasun_double_game_install(temp)

            install = resolve_manual_install(nested_game)

            self.assertIsNotNone(install)
            assert install is not None
            self.assertEqual(install.game_root, nested_game.resolve())
            self.assertEqual(install.paks_root, paks.resolve())
            self.assertEqual(install.launcher_exe, base / "launcher.exe")

    def test_manual_picker_accepts_double_game_paks_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _base, _game, nested_game, paks = self._make_seasun_double_game_install(temp)

            install = resolve_manual_install(paks)

            self.assertIsNotNone(install)
            assert install is not None
            self.assertEqual(install.game_root, nested_game.resolve())
            self.assertEqual(install.paks_root, paks.resolve())

    def test_standalone_launcher_can_live_in_seasun_base_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base, game, _paks = self._make_seasun_nested_install(temp)

            install = build_install_info(game, install_type="Standalone")

            self.assertIsNotNone(install)
            assert install is not None
            self.assertEqual(install.launcher_exe, base / "launcher.exe")

    def test_standalone_launcher_can_live_in_seasun_base_folder_for_double_game_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base, _game, nested_game, _paks = self._make_seasun_double_game_install(temp)

            install = build_install_info(nested_game, install_type="Standalone")

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


class _FakeRegistryKey:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


class _FakeWinreg:
    HKEY_LOCAL_MACHINE = object()
    KEY_READ = 1
    KEY_WOW64_64KEY = 0
    KEY_WOW64_32KEY = 0

    def __init__(self, keys: dict[str, dict[str, str]]) -> None:
        self.keys = keys

    def OpenKey(self, hive, subkey: str, reserved: int = 0, access: int = 0) -> _FakeRegistryKey:  # noqa: N802
        if subkey not in self.keys:
            raise OSError(subkey)
        return _FakeRegistryKey(self.keys[subkey])

    def QueryValueEx(self, key: _FakeRegistryKey, value_name: str):  # noqa: N802
        if value_name not in key.values:
            raise OSError(value_name)
        return key.values[value_name], None


if __name__ == "__main__":
    unittest.main()
