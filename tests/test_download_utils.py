from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import requests

import tests.context  # noqa: F401
from snowbreak_launcher.download_utils import DOWNLOAD_TIMEOUT, download_with_resume
from snowbreak_launcher.progress import OperationCancelled


class DownloadUtilsTests(unittest.TestCase):
    def test_connection_reset_during_stream_retries_and_resumes_partial_file(self) -> None:
        class ResetResponse:
            status_code = 200
            headers = {"Content-Length": "5"}

            def raise_for_status(self) -> None:
                return None

            def iter_content(self, chunk_size: int):
                yield b"he"
                raise requests.ConnectionError("connection reset")

        class ResumeResponse:
            status_code = 206
            headers = {"Content-Length": "3"}

            def raise_for_status(self) -> None:
                return None

            def iter_content(self, chunk_size: int):
                yield b"llo"

        calls: list[dict] = []
        responses = [ResetResponse(), ResumeResponse()]

        def fake_get(url: str, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "file.bin"

            result = download_with_resume(
                "https://example.invalid/file.bin",
                target,
                hashlib.sha256(b"hello").hexdigest(),
                expected_size=5,
                request_get=fake_get,
            )

            self.assertEqual(result.read_bytes(), b"hello")
            self.assertEqual([call.get("headers") for call in calls], [None, {"Range": "bytes=2-"}])
            self.assertEqual([call.get("timeout") for call in calls], [DOWNLOAD_TIMEOUT, DOWNLOAD_TIMEOUT])

    def test_cancelled_download_stops_before_retrying(self) -> None:
        class ResetResponse:
            status_code = 200
            headers = {"Content-Length": "5"}

            def raise_for_status(self) -> None:
                return None

            def iter_content(self, chunk_size: int):
                yield b"he"
                raise requests.ConnectionError("connection reset")

        cancelled = False
        calls = 0

        def fake_get(url: str, **kwargs):
            nonlocal calls
            calls += 1
            return ResetResponse()

        def cancel_check() -> bool:
            return cancelled

        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "file.bin"

            def progress(downloaded: int, total: int) -> None:
                nonlocal cancelled
                cancelled = True

            with self.assertRaises(OperationCancelled):
                download_with_resume(
                    "https://example.invalid/file.bin",
                    target,
                    hashlib.sha256(b"hello").hexdigest(),
                    expected_size=5,
                    request_get=fake_get,
                    progress=progress,
                    cancel_check=cancel_check,
                )

            self.assertEqual(calls, 1)
            self.assertTrue(target.with_suffix(".bin.download").exists())


if __name__ == "__main__":
    unittest.main()
