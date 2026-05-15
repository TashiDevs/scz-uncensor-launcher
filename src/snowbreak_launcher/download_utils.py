from __future__ import annotations

import hashlib
import os
from pathlib import Path

import requests

from .progress import OperationCancelled


DOWNLOAD_TIMEOUT = (10, 15)
DOWNLOAD_MAX_ATTEMPTS = 3


def download_with_resume(
    url: str,
    destination: Path,
    expected_sha256: str,
    *,
    expected_size: int = 0,
    session: requests.Session | None = None,
    request_get: callable | None = None,
    progress: callable | None = None,
    cancel_check: callable | None = None,
    hash_error: Exception | None = None,
) -> Path:
    last_error: Exception | None = None
    for attempt in range(DOWNLOAD_MAX_ATTEMPTS):
        _check_cancelled(cancel_check)
        try:
            return _download_once(
                url,
                destination,
                expected_sha256,
                expected_size=expected_size,
                session=session,
                request_get=request_get,
                progress=progress,
                cancel_check=cancel_check,
                hash_error=hash_error,
            )
        except Exception as exc:
            _check_cancelled(cancel_check)
            if not is_retryable_download_exception(exc) or attempt == DOWNLOAD_MAX_ATTEMPTS - 1:
                raise
            last_error = exc
    if last_error:
        raise last_error
    raise RuntimeError("Download failed before it could start.")


def _download_once(
    url: str,
    destination: Path,
    expected_sha256: str,
    *,
    expected_size: int = 0,
    session: requests.Session | None = None,
    request_get: callable | None = None,
    progress: callable | None = None,
    cancel_check: callable | None = None,
    hash_error: Exception | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(destination.suffix + ".download")
    partial_size = temp_path.stat().st_size if temp_path.exists() else 0
    headers = {"Range": f"bytes={partial_size}-"} if partial_size else None

    if request_get is not None:
        response = request_get(url, stream=True, timeout=DOWNLOAD_TIMEOUT, headers=headers)
    else:
        client = session or requests.Session()
        response = client.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT, headers=headers)
    response.raise_for_status()

    resumed = partial_size > 0 and getattr(response, "status_code", 200) == 206
    mode = "ab" if resumed else "wb"
    downloaded = partial_size if resumed else 0
    total = _total_size(response, downloaded, expected_size)

    digest = hashlib.sha256()
    if resumed:
        _update_digest_from_file(digest, temp_path)

    _check_cancelled(cancel_check)
    with temp_path.open(mode) as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            handle.write(chunk)
            digest.update(chunk)
            downloaded += len(chunk)
            if progress:
                progress(downloaded, total)
            _check_cancelled(cancel_check)

    actual = digest.hexdigest().lower()
    if actual != expected_sha256.lower():
        temp_path.unlink(missing_ok=True)
        raise hash_error or RuntimeError("Downloaded file hash mismatch.")

    os.replace(temp_path, destination)
    return destination


def is_retryable_download_exception(exc: BaseException) -> bool:
    if _is_hash_mismatch(exc):
        return True
    if isinstance(exc, requests.HTTPError):
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", 0) or 0
        return status in {408, 425, 429} or status >= 500
    return isinstance(
        exc,
        (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.ContentDecodingError,
            requests.exceptions.SSLError,
        ),
    )


def _check_cancelled(cancel_check: callable | None) -> None:
    if cancel_check and cancel_check():
        raise OperationCancelled("Cancelled by user.")


def _total_size(response: requests.Response, downloaded: int, expected_size: int) -> int:
    if expected_size:
        return expected_size
    content_length = int(response.headers.get("Content-Length") or 0)
    return downloaded + content_length if downloaded else content_length


def _update_digest_from_file(digest: "hashlib._Hash", path: Path) -> None:
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)


def _is_hash_mismatch(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "mismatch" in text and ("sha-256" in text or "hash" in text)
