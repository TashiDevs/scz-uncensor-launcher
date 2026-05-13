from __future__ import annotations

import tempfile
import unittest
import zipfile
import os
from pathlib import Path
from unittest.mock import patch

import tests.context  # noqa: F401
from snowbreak_launcher.constants import DEFAULT_STATIC_ASSET_SHA256, DEFAULT_STATIC_ASSET_URL, STATIC_ASSET_NAMES
from snowbreak_launcher.static_assets import StaticAssetError, configured_static_download, import_static_zip


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


if __name__ == "__main__":
    unittest.main()
