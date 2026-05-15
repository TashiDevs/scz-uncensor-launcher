from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

import requests

from .config import append_log, downloads_dir
from .constants import DEFAULT_STATIC_ASSET_SHA256, DEFAULT_STATIC_ASSET_URL, MANAGED_FOLDER_NAME, STATIC_ASSET_NAMES
from .download_utils import download_with_resume
from .github_client import file_sha256
from .models import LauncherState


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


def download_static_zip(
    url: str,
    expected_sha256: str,
    progress: callable | None = None,
    cancel_check: callable | None = None,
) -> Path:
    target = downloads_dir() / "snowbreak-static-assets.zip"
    return download_with_resume(
        url,
        target,
        expected_sha256,
        request_get=requests.get,
        progress=progress,
        cancel_check=cancel_check,
        hash_error=StaticAssetError("Static asset ZIP hash mismatch. The file was not installed."),
    )


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
                shutil.copyfileobj(source, output)
            installed.append(name)
            append_log(f"Imported static asset {name}")
    return sorted(installed)


def static_pack_is_current(ix_folder: Path, state: LauncherState, url: str, sha256: str) -> bool:
    if not _static_files_present(ix_folder):
        return False
    pack = state.static_asset_pack if isinstance(state.static_asset_pack, dict) else {}
    if not pack:
        return True
    expected = {"url": url, "sha256": sha256.lower()}
    if pack.get("url") != expected["url"] or pack.get("sha256") != expected["sha256"]:
        return False
    if "files" not in pack:
        return True
    return _static_files_match_record(ix_folder, pack.get("files"))


def remember_static_pack(ix_folder: Path, state: LauncherState, url: str, sha256: str) -> None:
    state.static_asset_pack = {
        "url": url,
        "sha256": sha256.lower(),
        "files": {
            name: file_sha256(ix_folder / name)
            for name in sorted(STATIC_ASSET_NAMES)
            if (ix_folder / name).is_file()
        },
    }


def _reject_unsafe_member(member_name: str) -> None:
    path = Path(member_name)
    if path.is_absolute() or ".." in path.parts:
        raise StaticAssetError(f"Unsafe ZIP path rejected: {member_name}")


def _validate_static_target(ix_folder: Path) -> None:
    if ix_folder.name.lower() != MANAGED_FOLDER_NAME.lower() or ix_folder.parent.name.lower() != "paks":
        raise StaticAssetError(f"Refusing to install static assets into unexpected folder: {ix_folder}")


def _static_files_present(ix_folder: Path) -> bool:
    return all((ix_folder / name).is_file() for name in STATIC_ASSET_NAMES)


def _static_files_match_record(ix_folder: Path, files: object) -> bool:
    if not isinstance(files, dict):
        return False
    for name in STATIC_ASSET_NAMES:
        expected_hash = files.get(name)
        if not isinstance(expected_hash, str) or not expected_hash:
            return False
        target = ix_folder / name
        if not target.is_file() or file_sha256(target).lower() != expected_hash.lower():
            return False
    return True
