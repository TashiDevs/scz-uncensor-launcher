from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import tests.context  # noqa: F401
from snowbreak_launcher.constants import STATIC_ASSET_NAMES
from snowbreak_launcher.installer import clean_managed_folder, static_asset_status, uncensor_file_status
from snowbreak_launcher.models import LauncherState


class InstallerTests(unittest.TestCase):
    def test_clean_managed_folder_preserves_only_static_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ix = Path(temp) / "Game" / "Content" / "Paks" / "~ix"
            ix.mkdir(parents=True)
            for name in STATIC_ASSET_NAMES:
                (ix / name).write_text("keep", encoding="utf-8")
            (ix / "old-uncensor.pak").write_text("remove", encoding="utf-8")
            nested = ix / "nested"
            nested.mkdir()
            (nested / "file.txt").write_text("remove", encoding="utf-8")

            removed = clean_managed_folder(ix)

            self.assertEqual({path.name for path in removed}, {"old-uncensor.pak", "nested"})
            for name in STATIC_ASSET_NAMES:
                self.assertTrue((ix / name).exists())
            self.assertFalse((ix / "old-uncensor.pak").exists())
            self.assertFalse(nested.exists())

    def test_static_status_reports_partial_install(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ix = Path(temp) / "Game" / "Content" / "Paks" / "~ix"
            ix.mkdir(parents=True)
            one_name = sorted(STATIC_ASSET_NAMES)[0]
            (ix / one_name).write_text("present", encoding="utf-8")

            ok, present = static_asset_status(ix)

            self.assertFalse(ok)
            self.assertEqual(present, [one_name])

    def test_uncensor_status_requires_tracked_files_to_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ix = Path(temp) / "Game" / "Content" / "Paks" / "~ix"
            ix.mkdir(parents=True)
            state = LauncherState(
                installed_release="AntiAmend-current",
                installed_files={"core-a.pak": "hash-a", "core-b.pak": "hash-b"},
            )
            (ix / "core-a.pak").write_text("present", encoding="utf-8")

            ok, present = uncensor_file_status(ix, state)

            self.assertFalse(ok)
            self.assertEqual(present, ["core-a.pak"])


if __name__ == "__main__":
    unittest.main()
