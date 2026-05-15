from __future__ import annotations

import hashlib
import re
from pathlib import Path

import requests

from .constants import GITHUB_RELEASE_API
from .download_utils import download_with_resume
from .models import GitHubAsset, GitHubRelease


class ReleaseError(RuntimeError):
    pass


def fetch_latest_release(session: requests.Session | None = None) -> GitHubRelease:
    client = session or requests.Session()
    response = client.get(
        GITHUB_RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "SnowbreakUncensorLauncher"},
        timeout=30,
    )
    response.raise_for_status()
    return parse_release(response.json())


def parse_release(data: dict) -> GitHubRelease:
    tag_name = str(data.get("tag_name") or "").strip()
    html_url = str(data.get("html_url") or "").strip()
    body = str(data.get("body") or "")
    if not tag_name:
        raise ReleaseError("GitHub release did not include a tag name.")

    body_hashes = _hashes_from_body(body)
    assets: list[GitHubAsset] = []
    for raw_asset in data.get("assets") or []:
        name = str(raw_asset.get("name") or "")
        if not name.lower().endswith(".pak"):
            continue
        _validate_asset_basename(name)
        digest = str(raw_asset.get("digest") or "")
        sha256 = ""
        if digest.startswith("sha256:"):
            sha256 = digest.split(":", 1)[1].lower()
        if not sha256:
            sha256 = body_hashes.get(name, "")
        if not re.fullmatch(r"[a-fA-F0-9]{64}", sha256):
            raise ReleaseError(f"Missing SHA-256 hash for GitHub asset: {name}")
        download_url = str(raw_asset.get("browser_download_url") or "")
        if not download_url:
            raise ReleaseError(f"Missing download URL for GitHub asset: {name}")
        assets.append(
            GitHubAsset(
                name=name,
                size=int(raw_asset.get("size") or 0),
                sha256=sha256.lower(),
                download_url=download_url,
            )
        )

    if not assets:
        raise ReleaseError("GitHub release did not contain any .pak assets.")
    return GitHubRelease(tag_name=tag_name, html_url=html_url, assets=tuple(assets))


def _validate_asset_basename(name: str) -> None:
    path = Path(name)
    if path.name != name or path.is_absolute() or ".." in path.parts or "/" in name or "\\" in name:
        raise ReleaseError(f"Unsafe GitHub asset name: {name}")


def download_asset(
    asset: GitHubAsset,
    destination: Path,
    session: requests.Session | None = None,
    progress: callable | None = None,
    cancel_check: callable | None = None,
) -> None:
    download_with_resume(
        asset.download_url,
        destination,
        asset.sha256,
        expected_size=asset.size,
        session=session,
        progress=(lambda downloaded, total: progress(asset.name, downloaded, total)) if progress else None,
        cancel_check=cancel_check,
        hash_error=ReleaseError(f"SHA-256 mismatch for {asset.name}. Download was not installed."),
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hashes_from_body(body: str) -> dict[str, str]:
    result: dict[str, str] = {}
    matches = re.finditer(
        r"\*\*(?P<name>[^*\r\n]+?\.pak)\*\*.*?SHA256:\s*`?(?P<hash>[a-fA-F0-9]{64})`?",
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in matches:
        result[match.group("name")] = match.group("hash").lower()
    return result
