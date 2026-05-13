from __future__ import annotations

import tempfile
import unittest
import zipfile
import os
from pathlib import Path
from unittest.mock import patch

import tests.context  # noqa: F401
from snowbreak_launcher.constants import DEFAULT_STATIC_ASSET_SHA256, DEFAULT_STATIC_ASSET_URL, STATIC_ASSET_NAMES
from snowbreak_launcher.github_client import file_sha256
from snowbreak_launcher.models import LauncherState
from snowbreak_launcher.static_assets import (
    StaticAssetError,
    configured_static_download,
    import_static_zip,
    remember_static_pack,
    static_pack_is_current,
)


class StaticAssetTests(unittest.TestCase):
    def test_configured_static_download_uses_builtin_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(configured_static_download(), (DEFAULT_STATIC_ASSET_URL, DEFAULT_STATIC_ASSET_SHA256))

    def test_configured_static_download_allows_env_override(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SBUL_STATIC_ASSET_URL": "https://example.invalid/assets.zip",
                "SBUL_STATIC_ASSET_SHA256": "ABCDEF",
            },
            clear=True,
        ):
            self.assertEqual(configured_static_download(), ("https://example.invalid/assets.zip", "abcdef"))

    def test_configured_static_download_rejects_partial_override(self) -> None:
        with patch.dict(os.environ, {"SBUL_STATIC_ASSET_URL": "https://example.invalid/assets.zip"}, clear=True):
            with self.assertRaises(StaticAssetError):
                configured_static_download()

    def test_import_static_zip_extracts_only_known_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            zip_path = root / "assets.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                for name in STATIC_ASSET_NAMES:
                    archive.writestr(f"folder/{name}", f"content-{name}")
                archive.writestr("folder/extra.pak", "ignore")

            ix = root / "Game" / "Content" / "Paks" / "~ix"
            installed = import_static_zip(zip_path, ix)

            self.assertEqual(set(installed), STATIC_ASSET_NAMES)
            for name in STATIC_ASSET_NAMES:
                self.assertTrue((ix / name).exists())
            self.assertFalse((ix / "extra.pak").exists())

    def test_import_static_zip_rejects_missing_static_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            zip_path = root / "assets.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(sorted(STATIC_ASSET_NAMES)[0], "only one")

            with self.assertRaises(StaticAssetError):
                import_static_zip(zip_path, root / "Game" / "Content" / "Paks" / "~ix")

    def test_import_static_zip_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            zip_path = root / "assets.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                for name in STATIC_ASSET_NAMES:
                    archive.writestr(name, "ok")
                archive.writestr("../character-anti-censorship_99_P.pak", "bad")

            with self.assertRaises(StaticAssetError):
                import_static_zip(zip_path, root / "Game" / "Content" / "Paks" / "~ix")

    def test_static_pack_current_when_url_and_hash_match_and_files_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ix = Path(temp) / "Game" / "Content" / "Paks" / "~ix"
            ix.mkdir(parents=True)
            for name in STATIC_ASSET_NAMES:
                (ix / name).write_text(name, encoding="utf-8")
            state = LauncherState(static_asset_pack={"url": "https://example.invalid/assets.zip", "sha256": "abc"})

            self.assertTrue(static_pack_is_current(ix, state, "https://example.invalid/assets.zip", "abc"))

    def test_static_pack_current_can_migrate_from_saved_file_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ix = Path(temp) / "Game" / "Content" / "Paks" / "~ix"
            ix.mkdir(parents=True)
            files: dict[str, str] = {}
            for name in STATIC_ASSET_NAMES:
                target = ix / name
                target.write_text(name, encoding="utf-8")
                files[name] = file_sha256(target)
            state = LauncherState(static_asset_pack={"url": "https://example.invalid/assets.zip", "sha256": "abc", "files": files})

            self.assertTrue(static_pack_is_current(ix, state, "https://example.invalid/assets.zip", "abc"))

    def test_static_pack_current_can_migrate_existing_files_without_prior_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ix = Path(temp) / "Game" / "Content" / "Paks" / "~ix"
            ix.mkdir(parents=True)
            for name in STATIC_ASSET_NAMES:
                (ix / name).write_text(name, encoding="utf-8")

            self.assertTrue(static_pack_is_current(ix, LauncherState(), "https://example.invalid/assets.zip", "abc"))

    def test_static_pack_current_rejects_changed_pack_hash_even_when_files_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ix = Path(temp) / "Game" / "Content" / "Paks" / "~ix"
            ix.mkdir(parents=True)
            files: dict[str, str] = {}
            for name in STATIC_ASSET_NAMES:
                target = ix / name
                target.write_text(name, encoding="utf-8")
                files[name] = file_sha256(target)
            state = LauncherState(static_asset_pack={"url": "https://example.invalid/assets.zip", "sha256": "old", "files": files})

            self.assertFalse(static_pack_is_current(ix, state, "https://example.invalid/assets.zip", "new"))

    def test_static_pack_current_rejects_changed_static_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ix = Path(temp) / "Game" / "Content" / "Paks" / "~ix"
            ix.mkdir(parents=True)
            for name in STATIC_ASSET_NAMES:
                (ix / name).write_text(name, encoding="utf-8")
            state = LauncherState()
            remember_static_pack(ix, state, "https://example.invalid/assets.zip", "abc")
            (ix / sorted(STATIC_ASSET_NAMES)[0]).write_text("changed", encoding="utf-8")

            self.assertFalse(static_pack_is_current(ix, state, "https://example.invalid/assets.zip", "different"))


if __name__ == "__main__":
    unittest.main()
