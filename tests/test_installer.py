from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tests.context  # noqa: F401
from snowbreak_launcher.installer import (
    clean_managed_folder,
    mod_folder_warnings,
    obsolete_managed_items,
    setup_or_update,
    uncensor_file_status,
)
from snowbreak_launcher.models import GitHubAsset, GitHubRelease, InstallInfo, LauncherState


LEGACY_STATIC_ASSET_NAMES = {
    "character-anti-censorship_99_P.pak",
    "illustration-anti-censorship_99_P.pak",
}


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

    def test_clean_managed_folder_removes_old_static_assets_when_not_in_release(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ix = Path(temp) / "Game" / "Content" / "Paks" / "~ix"
            ix.mkdir(parents=True)
            for name in LEGACY_STATIC_ASSET_NAMES:
                (ix / name).write_text("remove", encoding="utf-8")
            (ix / "current-core.pak").write_text("keep", encoding="utf-8")
            nested = ix / "nested"
            nested.mkdir()
            (nested / "file.txt").write_text("remove", encoding="utf-8")

            removed = clean_managed_folder(ix, preserve_names={"current-core.pak"})

            self.assertEqual({path.name for path in removed}, {*LEGACY_STATIC_ASSET_NAMES, "nested"})
            for name in LEGACY_STATIC_ASSET_NAMES:
                self.assertFalse((ix / name).exists())
            self.assertTrue((ix / "current-core.pak").exists())
            self.assertFalse(nested.exists())

    def test_clean_managed_folder_clears_readonly_before_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ix = Path(temp) / "Game" / "Content" / "Paks" / "~ix"
            ix.mkdir(parents=True)
            target = ix / "old-core.pak"
            target.write_text("remove", encoding="utf-8")

            with patch("snowbreak_launcher.installer.clear_readonly_for_launcher_path") as clear_readonly:
                clean_managed_folder(ix, preserve_names={"current-core.pak"})

            clear_readonly.assert_called_once_with(target, ix_folder=ix)

    def test_setup_update_clears_paks_root_before_creating_ix_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install = self._install(root)
            install.paks_root.mkdir(parents=True)
            install.localization_path.parent.mkdir(parents=True)
            install.localization_path.write_text("localization = 1\n", encoding="utf-8")
            release = GitHubRelease("AntiAmend-new", "https://example.invalid", assets=())

            with (
                patch("snowbreak_launcher.installer.fetch_latest_release", return_value=release),
                patch("snowbreak_launcher.installer.clear_readonly_for_launcher_path") as clear_readonly,
                patch("snowbreak_launcher.installer.save_state"),
            ):
                setup_or_update(install, LauncherState())

            clear_readonly.assert_any_call(install.paks_root, paks_root=install.paks_root)
            self.assertTrue(install.ix_folder.exists())

    def test_obsolete_managed_items_reports_old_static_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ix = Path(temp) / "Game" / "Content" / "Paks" / "~ix"
            ix.mkdir(parents=True)
            for name in LEGACY_STATIC_ASSET_NAMES:
                (ix / name).write_text("old static", encoding="utf-8")
            (ix / "current-core.pak").write_text("keep", encoding="utf-8")

            obsolete = obsolete_managed_items(ix, {"current-core.pak"})

            self.assertEqual({path.name for path in obsolete}, LEGACY_STATIC_ASSET_NAMES)

    def test_mod_folder_warnings_reports_direct_non_ix_folders_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paks = Path(temp) / "Game" / "Content" / "Paks"
            paks.mkdir(parents=True)
            (paks / "~ix").mkdir()
            (paks / "LegacyUncensor").mkdir()
            (paks / "core.pak").write_text("pak", encoding="utf-8")
            (paks / "LegacyUncensor" / "nested").mkdir()

            warnings = mod_folder_warnings(paks)

            self.assertEqual(warnings, ["LegacyUncensor"])

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

    def test_setup_update_does_not_require_static_asset_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install = self._install(root)
            install.paks_root.mkdir(parents=True)
            install.localization_path.parent.mkdir(parents=True)
            install.localization_path.write_text("localization = 1\n", encoding="utf-8")
            install.ix_folder.mkdir(parents=True)

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
                patch("snowbreak_launcher.installer.download_asset", side_effect=fake_download_asset),
                patch("snowbreak_launcher.installer.file_sha256", return_value="core-hash"),
                patch("snowbreak_launcher.installer._fresh_staging_dir", return_value=staging),
                patch("snowbreak_launcher.installer.save_state"),
            ):
                updated = setup_or_update(install, state)

            self.assertEqual(updated.installed_release, "AntiAmend-new")
            self.assertEqual(updated.static_asset_pack, {})

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
                updated = setup_or_update(install, state)

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
                updated = setup_or_update(install, LauncherState(installed_release="AntiAmend-old"))

            self.assertEqual(downloaded, ["core-b.pak", "core-c.pak"])
            self.assertEqual((install.ix_folder / "core-a.pak").read_text(encoding="utf-8"), "core-a-current")
            self.assertEqual((install.ix_folder / "core-b.pak").read_text(encoding="utf-8"), "core-b-new")
            self.assertEqual((install.ix_folder / "core-c.pak").read_text(encoding="utf-8"), "core-c-new")
            self.assertFalse((install.ix_folder / "removed-core.pak").exists())
            self.assertEqual(set(updated.installed_files), {"core-a.pak", "core-b.pak", "core-c.pak"})

    def test_setup_update_clears_readonly_before_overwriting_existing_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install = self._install(root)
            install.paks_root.mkdir(parents=True)
            install.localization_path.parent.mkdir(parents=True)
            install.localization_path.write_text("localization = 1\n", encoding="utf-8")
            install.ix_folder.mkdir(parents=True)
            target = install.ix_folder / "core.pak"
            target.write_text("old", encoding="utf-8")
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
                patch("snowbreak_launcher.installer.download_asset", side_effect=fake_download_asset),
                patch("snowbreak_launcher.installer.clear_readonly_for_launcher_path") as clear_readonly,
                patch("snowbreak_launcher.installer.save_state"),
            ):
                setup_or_update(install, LauncherState(installed_release="AntiAmend-old"))

            clear_readonly.assert_any_call(target, ix_folder=install.ix_folder)

    def test_setup_update_removes_old_static_assets_from_ix(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install = self._install(root)
            install.paks_root.mkdir(parents=True)
            install.localization_path.parent.mkdir(parents=True)
            install.localization_path.write_text("localization = 1\n", encoding="utf-8")
            install.ix_folder.mkdir(parents=True)
            for name in LEGACY_STATIC_ASSET_NAMES:
                (install.ix_folder / name).write_text("old static", encoding="utf-8")
            (install.ix_folder / "core.pak").write_text("core-current", encoding="utf-8")

            release = GitHubRelease(
                tag_name="AntiAmend-new",
                html_url="https://example.invalid",
                assets=(GitHubAsset("core.pak", 12, self._sha("core-current"), "https://example.invalid/core.pak"),),
            )

            with (
                patch("snowbreak_launcher.installer.fetch_latest_release", return_value=release),
                patch("snowbreak_launcher.installer.download_asset") as download_asset,
                patch("snowbreak_launcher.installer.save_state"),
            ):
                updated = setup_or_update(install, LauncherState(installed_release="AntiAmend-old"))

            download_asset.assert_not_called()
            for name in LEGACY_STATIC_ASSET_NAMES:
                self.assertFalse((install.ix_folder / name).exists())
            self.assertEqual(updated.installed_files, {"core.pak": self._sha("core-current")})

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
                setup_or_update(install, LauncherState())

            self.assertFalse(staging.exists())

if __name__ == "__main__":
    unittest.main()
