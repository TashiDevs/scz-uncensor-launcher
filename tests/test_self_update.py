from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tests.context  # noqa: F401
from snowbreak_launcher.self_update import (
    SelfUpdateError,
    apply_self_update,
    is_newer_version,
    parse_launcher_release,
    prepare_self_update,
)


class SelfUpdateTests(unittest.TestCase):
    def _release(self, tag: str, *, digest: str = "", body: str = "") -> dict:
        return {
            "tag_name": tag,
            "html_url": "https://example.invalid/release",
            "body": body,
            "assets": [
                {
                    "name": "SnowbreakUncensorLauncher.exe",
                    "size": 123,
                    "digest": f"sha256:{digest}" if digest else "",
                    "browser_download_url": "https://example.invalid/SnowbreakUncensorLauncher.exe",
                }
            ],
        }

    def test_version_comparison(self) -> None:
        self.assertTrue(is_newer_version("v1.04", "1.03"))
        self.assertTrue(is_newer_version("1.3.1", "1.3"))
        self.assertFalse(is_newer_version("v1.03", "1.03"))
        self.assertFalse(is_newer_version("not-a-version", "1.03"))

    def test_parse_release_uses_asset_digest(self) -> None:
        sha = "a" * 64
        update = parse_launcher_release(self._release("v1.04", digest=sha), current_version="1.03")

        self.assertIsNotNone(update)
        self.assertEqual(update.asset_sha256, sha)
        self.assertEqual(update.asset_name, "SnowbreakUncensorLauncher.exe")

    def test_parse_release_uses_body_hash(self) -> None:
        sha = "b" * 64
        update = parse_launcher_release(self._release("v1.04", body=f"SHA-256:\n{sha}"), current_version="1.03")

        self.assertIsNotNone(update)
        self.assertEqual(update.asset_sha256, sha)

    def test_parse_release_ignores_current_or_older_release(self) -> None:
        self.assertIsNone(parse_launcher_release(self._release("v1.03", digest="a" * 64), current_version="1.03"))

    def test_parse_release_requires_hash_for_newer_release(self) -> None:
        with self.assertRaises(SelfUpdateError):
            parse_launcher_release(self._release("v1.04"), current_version="1.03")

    def test_prepare_self_update_copies_current_exe_and_starts_helper_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current = root / "SnowbreakUncensorLauncher.exe"
            downloaded = root / "downloaded.exe"
            current.write_text("current", encoding="utf-8")
            downloaded.write_text("new", encoding="utf-8")
            commands: list[list[str]] = []

            def fake_popen(command: list[str], **kwargs) -> None:
                commands.append(command)

            with (
                patch("snowbreak_launcher.self_update.app_data_dir", return_value=root / "appdata"),
                patch("snowbreak_launcher.self_update.append_log"),
            ):
                updater = prepare_self_update(
                    downloaded,
                    expected_sha256="a" * 64,
                    current_exe=current,
                    current_pid=1234,
                    popen=fake_popen,
                )

            self.assertTrue(updater.is_file())
            self.assertEqual(updater.read_text(encoding="utf-8"), "current")
            self.assertEqual(commands[0][1], "--apply-update")
            self.assertIn(str(downloaded), commands[0])
            self.assertIn(str(current), commands[0])
            self.assertIn("1234", commands[0])
            self.assertIn("--update-sha256", commands[0])
            self.assertIn("a" * 64, commands[0])

    def test_apply_self_update_replaces_target_without_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "new.exe"
            target = root / "old.exe"
            source.write_text("new", encoding="utf-8")
            target.write_text("old", encoding="utf-8")

            with patch("snowbreak_launcher.self_update.app_data_dir", return_value=root / "appdata"):
                result = apply_self_update(source, target, restart=False)

            self.assertEqual(result, 0)
            self.assertEqual(target.read_text(encoding="utf-8"), "new")
            self.assertFalse(source.exists())

    def test_apply_self_update_uses_target_sibling_temp_before_replace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "downloads" / "new.exe"
            target = root / "different-folder" / "SnowbreakUncensorLauncher.exe"
            source.parent.mkdir(parents=True)
            target.parent.mkdir(parents=True)
            source.write_text("new", encoding="utf-8")
            target.write_text("old", encoding="utf-8")
            expected_hash = hashlib.sha256(b"new").hexdigest()
            calls: list[tuple[Path, Path]] = []

            def fake_replace(src: Path, dst: Path) -> None:
                calls.append((Path(src), Path(dst)))
                Path(dst).write_bytes(Path(src).read_bytes())
                Path(src).unlink()

            with (
                patch("snowbreak_launcher.self_update.os.replace", side_effect=fake_replace),
                patch("snowbreak_launcher.self_update.app_data_dir", return_value=root / "appdata"),
            ):
                result = apply_self_update(source, target, expected_sha256=expected_hash, restart=False)

            self.assertEqual(result, 0)
            self.assertEqual(calls, [(target.with_name(target.name + ".new"), target)])
            self.assertEqual(target.read_text(encoding="utf-8"), "new")
            self.assertFalse(source.exists())

    def test_apply_self_update_cleans_download_and_updater_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            appdata = root / "appdata"
            source = appdata / "downloads" / "launcher-updates" / "v1.05" / "SnowbreakUncensorLauncher.exe"
            target = root / "launcher" / "SnowbreakUncensorLauncher.exe"
            updater = appdata / "updater"
            source.parent.mkdir(parents=True)
            target.parent.mkdir(parents=True)
            updater.mkdir(parents=True)
            source.write_text("new", encoding="utf-8")
            target.write_text("old", encoding="utf-8")
            (updater / "SnowbreakLauncherUpdater.exe").write_text("helper", encoding="utf-8")

            with patch("snowbreak_launcher.self_update.app_data_dir", return_value=appdata):
                result = apply_self_update(source, target, restart=False)

            self.assertEqual(result, 0)
            self.assertEqual(target.read_text(encoding="utf-8"), "new")
            self.assertFalse((appdata / "downloads").exists())
            self.assertFalse(updater.exists())


if __name__ == "__main__":
    unittest.main()
