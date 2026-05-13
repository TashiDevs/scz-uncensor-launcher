from __future__ import annotations

import unittest

import tests.context  # noqa: F401
from snowbreak_launcher.github_client import ReleaseError, parse_release


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


if __name__ == "__main__":
    unittest.main()
