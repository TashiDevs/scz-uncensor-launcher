from __future__ import annotations

import unittest
import hashlib
import tempfile
from pathlib import Path

import tests.context  # noqa: F401
from snowbreak_launcher.github_client import ReleaseError, download_asset, parse_release
from snowbreak_launcher.models import GitHubAsset


class GitHubClientTests(unittest.TestCase):
    def test_parse_release_uses_digest_hash(self) -> None:
        sha = "a" * 64
        release = parse_release(
            {
                "tag_name": "AntiAmend-test",
                "html_url": "https://example.invalid/release",
                "assets": [
                    {
                        "name": "Patch_Xpand_AntiAmend_Test_100_P.pak",
                        "size": 123,
                        "digest": f"sha256:{sha}",
                        "browser_download_url": "https://example.invalid/file.pak",
                    }
                ],
            }
        )

        self.assertEqual(release.tag_name, "AntiAmend-test")
        self.assertEqual(release.assets[0].sha256, sha)

    def test_parse_release_accepts_arbitrary_pak_basenames(self) -> None:
        sha = "c" * 64
        release = parse_release(
            {
                "tag_name": "AntiAmend-test",
                "html_url": "https://example.invalid/release",
                "assets": [
                    {
                        "name": "brand_new_uncensor_file_123_P.pak",
                        "size": 123,
                        "digest": f"sha256:{sha}",
                        "browser_download_url": "https://example.invalid/new.pak",
                    }
                ],
            }
        )

        self.assertEqual(release.assets[0].name, "brand_new_uncensor_file_123_P.pak")

    def test_parse_release_can_read_hash_from_body(self) -> None:
        sha = "b" * 64
        release = parse_release(
            {
                "tag_name": "AntiAmend-test",
                "html_url": "https://example.invalid/release",
                "body": f"**Patch_Test.pak**\nSHA256: `{sha}`",
                "assets": [
                    {
                        "name": "Patch_Test.pak",
                        "size": 123,
                        "browser_download_url": "https://example.invalid/file.pak",
                    }
                ],
            }
        )

        self.assertEqual(release.assets[0].sha256, sha)

    def test_missing_hash_is_rejected(self) -> None:
        with self.assertRaises(ReleaseError):
            parse_release(
                {
                    "tag_name": "AntiAmend-test",
                    "assets": [
                        {
                            "name": "Patch_Test.pak",
                            "browser_download_url": "https://example.invalid/file.pak",
                        }
                    ],
                }
            )

    def test_path_shaped_pak_asset_names_are_rejected(self) -> None:
        sha = "d" * 64
        for name in ("folder/file.pak", r"..\file.pak", "../file.pak", "/tmp/file.pak"):
            with self.subTest(name=name):
                with self.assertRaises(ReleaseError):
                    parse_release(
                        {
                            "tag_name": "AntiAmend-test",
                            "assets": [
                                {
                                    "name": name,
                                    "digest": f"sha256:{sha}",
                                    "browser_download_url": "https://example.invalid/file.pak",
                                }
                            ],
                        }
                    )

    def test_non_pak_assets_are_ignored(self) -> None:
        sha = "e" * 64
        release = parse_release(
            {
                "tag_name": "AntiAmend-test",
                "assets": [
                    {
                        "name": "notes.txt",
                        "digest": f"sha256:{sha}",
                        "browser_download_url": "https://example.invalid/notes.txt",
                    },
                    {
                        "name": "Patch_Test.pak",
                        "digest": f"sha256:{sha}",
                        "browser_download_url": "https://example.invalid/file.pak",
                    },
                ],
            }
        )

        self.assertEqual([asset.name for asset in release.assets], ["Patch_Test.pak"])

    def test_download_asset_resumes_existing_partial_download(self) -> None:
        class FakeResponse:
            status_code = 206
            headers = {"Content-Length": "3"}

            def raise_for_status(self) -> None:
                return None

            def iter_content(self, chunk_size: int):
                yield b"llo"

        class FakeSession:
            def __init__(self) -> None:
                self.headers: dict | None = None

            def get(self, url: str, **kwargs):
                self.headers = kwargs.get("headers")
                return FakeResponse()

        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "core.pak"
            partial = destination.with_suffix(".pak.download")
            partial.write_bytes(b"he")
            session = FakeSession()
            asset = GitHubAsset(
                name="core.pak",
                size=5,
                sha256=hashlib.sha256(b"hello").hexdigest(),
                download_url="https://example.invalid/core.pak",
            )

            download_asset(asset, destination, session=session)

            self.assertEqual(session.headers, {"Range": "bytes=2-"})
            self.assertEqual(destination.read_bytes(), b"hello")
            self.assertFalse(partial.exists())

    def test_download_asset_restarts_when_server_ignores_resume(self) -> None:
        class FakeResponse:
            status_code = 200
            headers = {"Content-Length": "5"}

            def raise_for_status(self) -> None:
                return None

            def iter_content(self, chunk_size: int):
                yield b"hello"

        class FakeSession:
            def __init__(self) -> None:
                self.headers: dict | None = None

            def get(self, url: str, **kwargs):
                self.headers = kwargs.get("headers")
                return FakeResponse()

        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "core.pak"
            partial = destination.with_suffix(".pak.download")
            partial.write_bytes(b"bad-partial")
            session = FakeSession()
            asset = GitHubAsset(
                name="core.pak",
                size=5,
                sha256=hashlib.sha256(b"hello").hexdigest(),
                download_url="https://example.invalid/core.pak",
            )

            download_asset(asset, destination, session=session)

            self.assertEqual(session.headers, {"Range": "bytes=11-"})
            self.assertEqual(destination.read_bytes(), b"hello")
            self.assertFalse(partial.exists())


if __name__ == "__main__":
    unittest.main()
