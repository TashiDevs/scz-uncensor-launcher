from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tests.context  # noqa: F401
from snowbreak_launcher.constants import STATIC_ASSET_NAMES
from snowbreak_launcher.installer import clean_managed_folder, setup_or_update, static_asset_status, uncensor_file_status
from snowbreak_launcher.models import GitHubAsset, GitHubRelease, InstallInfo, LauncherState


class InstallerTests(unittest.TestCase):
    def _sha(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _install(self, root: Path) -> InstallInfo:
        return InstallInfo(
            install_type="Standalone",
            game_root=root,
            paks_root=root / "Game" / "Content" / "Paks",
            ix_folder=root / "Game" / "Content" / "Paks" / "~ix",
            localization_path=root / "Game" / "cbjq" / "localization.txt",
        )

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
                installed_files={"core-a.pak": self._sha("present"), "core-b.pak": "hash-b"},
            )
            (ix / "core-a.pak").write_text("present", encoding="utf-8")

            ok, present = uncensor_file_status(ix, state)

            self.assertFalse(ok)
            self.assertEqual(present, ["core-a.pak"])

    def test_setup_update_skips_static_download_when_pack_is_current(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install = self._install(root)
            install.paks_root.mkdir(parents=True)
            install.localization_path.parent.mkdir(parents=True)
            install.localization_path.write_text("localization = 1\n", encoding="utf-8")
            install.ix_folder.mkdir(parents=True)
            for name in STATIC_ASSET_NAMES:
                (install.ix_folder / name).write_text(f"static-{name}", encoding="utf-8")

            release = GitHubRelease(
                tag_name="AntiAmend-new",
                html_url="https://example.invalid",
                assets=(GitHubAsset("core.pak", 4, "core-hash", "https://example.invalid/core.pak"),),
            )
            staging = root / "staging"
            staging.mkdir()
            state = LauncherState(
                installed_release="AntiAmend-old",
                static_asset_pack={"url": "https://example.invalid/static.zip", "sha256": "static-hash"},
            )

            def fake_download_asset(asset: GitHubAsset, destination: Path, *args, **kwargs) -> None:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("core", encoding="utf-8")

            with (
                patch("snowbreak_launcher.installer.fetch_latest_release", return_value=release),
                patch("snowbreak_launcher.installer.configured_static_download", return_value=("https://example.invalid/static.zip", "static-hash")),
                patch("snowbreak_launcher.installer.download_asset", side_effect=fake_download_asset),
                patch("snowbreak_launcher.installer.file_sha256", return_value="core-hash"),
                patch("snowbreak_launcher.installer._fresh_staging_dir", return_value=staging),
                patch("snowbreak_launcher.installer.download_static_zip") as download_static_zip,
                patch("snowbreak_launcher.installer.import_static_zip") as import_static_zip,
                patch("snowbreak_launcher.installer.save_state"),
            ):
                updated = setup_or_update(install, state)

            download_static_zip.assert_not_called()
            import_static_zip.assert_not_called()
            self.assertEqual(updated.installed_release, "AntiAmend-new")
            self.assertEqual(updated.static_asset_pack["sha256"], "static-hash")

    def test_setup_update_skips_unchanged_github_asset_and_removes_obsolete(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install = self._install(root)
            install.paks_root.mkdir(parents=True)
            install.localization_path.parent.mkdir(parents=True)
            install.localization_path.write_text("localization = 1\n", encoding="utf-8")
            install.ix_folder.mkdir(parents=True)
            (install.ix_folder / "core-a.pak").write_text("core-a-current", encoding="utf-8")
            (install.ix_folder / "old-core.pak").write_text("old-core", encoding="utf-8")

            release = GitHubRelease(
                tag_name="AntiAmend-new",
                html_url="https://example.invalid",
                assets=(
                    GitHubAsset(
                        "core-a.pak",
                        14,
                        self._sha("core-a-current"),
                        "https://example.invalid/core-a.pak",
                    ),
                ),
            )
            state = LauncherState(installed_release="AntiAmend-old")

            with (
                patch("snowbreak_launcher.installer.fetch_latest_release", return_value=release),
                patch("snowbreak_launcher.installer.download_asset") as download_asset,
                patch("snowbreak_launcher.installer.save_state"),
            ):
                updated = setup_or_update(install, state, install_static_pack=False)

            download_asset.assert_not_called()
            self.assertTrue((install.ix_folder / "core-a.pak").is_file())
            self.assertFalse((install.ix_folder / "old-core.pak").exists())
            self.assertEqual(updated.installed_files, {"core-a.pak": self._sha("core-a-current")})

    def test_setup_update_downloads_only_changed_or_new_github_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install = self._install(root)
            install.paks_root.mkdir(parents=True)
            install.localization_path.parent.mkdir(parents=True)
            install.localization_path.write_text("localization = 1\n", encoding="utf-8")
            install.ix_folder.mkdir(parents=True)
            (install.ix_folder / "core-a.pak").write_text("core-a-current", encoding="utf-8")
            (install.ix_folder / "core-b.pak").write_text("core-b-old", encoding="utf-8")
            (install.ix_folder / "removed-core.pak").write_text("removed", encoding="utf-8")

            release = GitHubRelease(
                tag_name="AntiAmend-new",
                html_url="https://example.invalid",
                assets=(
                    GitHubAsset("core-a.pak", 14, self._sha("core-a-current"), "https://example.invalid/core-a.pak"),
                    GitHubAsset("core-b.pak", 10, self._sha("core-b-new"), "https://example.invalid/core-b.pak"),
                    GitHubAsset("core-c.pak", 10, self._sha("core-c-new"), "https://example.invalid/core-c.pak"),
                ),
            )
            downloaded: list[str] = []

            def fake_download_asset(asset: GitHubAsset, destination: Path, *args, **kwargs) -> None:
                downloaded.append(asset.name)
                content = {"core-b.pak": "core-b-new", "core-c.pak": "core-c-new"}[asset.name]
                destination.write_text(content, encoding="utf-8")

            with (
                patch("snowbreak_launcher.installer.fetch_latest_release", return_value=release),
                patch("snowbreak_launcher.installer.download_asset", side_effect=fake_download_asset),
                patch("snowbreak_launcher.installer.save_state"),
            ):
                updated = setup_or_update(install, LauncherState(installed_release="AntiAmend-old"), install_static_pack=False)

            self.assertEqual(downloaded, ["core-b.pak", "core-c.pak"])
            self.assertEqual((install.ix_folder / "core-a.pak").read_text(encoding="utf-8"), "core-a-current")
            self.assertEqual((install.ix_folder / "core-b.pak").read_text(encoding="utf-8"), "core-b-new")
            self.assertEqual((install.ix_folder / "core-c.pak").read_text(encoding="utf-8"), "core-c-new")
            self.assertFalse((install.ix_folder / "removed-core.pak").exists())
            self.assertEqual(set(updated.installed_files), {"core-a.pak", "core-b.pak", "core-c.pak"})

    def test_setup_update_removes_github_staging_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install = self._install(root)
            install.paks_root.mkdir(parents=True)
            install.localization_path.parent.mkdir(parents=True)
            install.localization_path.write_text("localization = 1\n", encoding="utf-8")
            install.ix_folder.mkdir(parents=True)
            staging = root / "staging"
            release = GitHubRelease(
                tag_name="AntiAmend-new",
                html_url="https://example.invalid",
                assets=(GitHubAsset("core.pak", 4, self._sha("core"), "https://example.invalid/core.pak"),),
            )

            def fake_download_asset(asset: GitHubAsset, destination: Path, *args, **kwargs) -> None:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("core", encoding="utf-8")

            with (
                patch("snowbreak_launcher.installer.fetch_latest_release", return_value=release),
                patch("snowbreak_launcher.installer._fresh_staging_dir", return_value=staging),
                patch("snowbreak_launcher.installer.download_asset", side_effect=fake_download_asset),
                patch("snowbreak_launcher.installer.save_state"),
            ):
                setup_or_update(install, LauncherState(), install_static_pack=False)

            self.assertFalse(staging.exists())

    def test_setup_update_removes_static_zip_after_import(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install = self._install(root)
            install.paks_root.mkdir(parents=True)
            install.localization_path.parent.mkdir(parents=True)
            install.localization_path.write_text("localization = 1\n", encoding="utf-8")
            install.ix_folder.mkdir(parents=True)
            zip_path = root / "downloads" / "snowbreak-static-assets.zip"
            zip_path.parent.mkdir()
            zip_path.write_text("zip", encoding="utf-8")
            release = GitHubRelease("AntiAmend-new", "https://example.invalid", assets=())

            def fake_import_static_zip(path: Path, ix_folder: Path) -> list[str]:
                for name in STATIC_ASSET_NAMES:
                    (ix_folder / name).write_text(name, encoding="utf-8")
                return sorted(STATIC_ASSET_NAMES)

            with (
                patch("snowbreak_launcher.installer.fetch_latest_release", return_value=release),
                patch("snowbreak_launcher.installer.configured_static_download", return_value=("https://example.invalid/static.zip", "static-hash")),
                patch("snowbreak_launcher.installer.download_static_zip", return_value=zip_path),
                patch("snowbreak_launcher.installer.import_static_zip", side_effect=fake_import_static_zip),
                patch("snowbreak_launcher.installer.save_state"),
            ):
                setup_or_update(install, LauncherState())

            self.assertFalse(zip_path.exists())


if __name__ == "__main__":
    unittest.main()
