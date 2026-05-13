from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path

import requests

from .config import append_log, downloads_dir
from .constants import DEFAULT_STATIC_ASSET_SHA256, DEFAULT_STATIC_ASSET_URL, MANAGED_FOLDER_NAME, STATIC_ASSET_NAMES


class StaticAssetError(RuntimeError):
    pass


def configured_static_download() -> tuple[str, str] | None:
    url_override = os.environ.get("SBUL_STATIC_ASSET_URL", "").strip()
    sha_override = os.environ.get("SBUL_STATIC_ASSET_SHA256", "").strip().lower()
    if url_override or sha_override:
        if not url_override or not sha_override:
            raise StaticAssetError("Static asset override needs both SBUL_STATIC_ASSET_URL and SBUL_STATIC_ASSET_SHA256.")
        return url_override, sha_override
    return DEFAULT_STATIC_ASSET_URL, DEFAULT_STATIC_ASSET_SHA256


def download_static_zip(url: str, expected_sha256: str, progress: callable | None = None) -> Path:
    target = downloads_dir() / "snowbreak-static-assets.zip"
    temp = target.with_suffix(".zip.download")
    temp.unlink(missing_ok=True)

    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()

    digest = hashlib.sha256()
    total = int(response.headers.get("Content-Length") or 0)
    downloaded = 0
    with temp.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            handle.write(chunk)
            digest.update(chunk)
            downloaded += len(chunk)
            if progress:
                progress(downloaded, total)

    actual = digest.hexdigest()
    if actual.lower() != expected_sha256.lower():
        temp.unlink(missing_ok=True)
        raise StaticAssetError("Static asset ZIP hash mismatch. The file was not installed.")

    os.replace(temp, target)
    return target


def import_static_zip(zip_path: Path, ix_folder: Path) -> list[str]:
    _validate_static_target(ix_folder)
    ix_folder.mkdir(parents=True, exist_ok=True)
    found: dict[str, zipfile.ZipInfo] = {}

    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename).name
            if name not in STATIC_ASSET_NAMES:
                continue
            _reject_unsafe_member(info.filename)
            found[name] = info

        missing = sorted(STATIC_ASSET_NAMES - set(found))
        if missing:
            raise StaticAssetError("Static asset ZIP is missing: " + ", ".join(missing))

        installed: list[str] = []
        for name, info in found.items():
            target = ix_folder / name
            with archive.open(info) as source, target.open("wb") as output:
                output.write(source.read())
            installed.append(name)
            append_log(f"Imported static asset {name}")
    return sorted(installed)


def _reject_unsafe_member(member_name: str) -> None:
    path = Path(member_name)
    if path.is_absolute() or ".." in path.parts:
        raise StaticAssetError(f"Unsafe ZIP path rejected: {member_name}")


def _validate_static_target(ix_folder: Path) -> None:
    if ix_folder.name.lower() != MANAGED_FOLDER_NAME.lower() or ix_folder.parent.name.lower() != "paks":
        raise StaticAssetError(f"Refusing to install static assets into unexpected folder: {ix_folder}")
