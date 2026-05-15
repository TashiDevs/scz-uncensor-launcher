from __future__ import annotations

import argparse
import ctypes
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from .config import app_data_dir, append_log, downloads_dir
from .constants import APP_VERSION, LAUNCHER_EXE_NAME, LAUNCHER_RELEASE_API
from .download_utils import download_with_resume


class SelfUpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class LauncherUpdateInfo:
    tag_name: str
    html_url: str
    asset_name: str
    asset_size: int
    asset_sha256: str
    download_url: str


def is_packaged_app() -> bool:
    return bool(getattr(sys, "frozen", False)) and Path(sys.executable).suffix.lower() == ".exe"


def is_newer_version(latest_tag: str, current_version: str = APP_VERSION) -> bool:
    latest = _version_tuple(latest_tag)
    current = _version_tuple(current_version)
    if latest is None or current is None:
        return False
    width = max(len(latest), len(current))
    return latest + (0,) * (width - len(latest)) > current + (0,) * (width - len(current))


def fetch_launcher_update(session: requests.Session | None = None, current_version: str = APP_VERSION) -> LauncherUpdateInfo | None:
    client = session or requests.Session()
    response = client.get(
        LAUNCHER_RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "SnowbreakUncensorLauncher"},
        timeout=30,
    )
    response.raise_for_status()
    return parse_launcher_release(response.json(), current_version=current_version)


def parse_launcher_release(data: dict, current_version: str = APP_VERSION) -> LauncherUpdateInfo | None:
    tag_name = str(data.get("tag_name") or "").strip()
    if not is_newer_version(tag_name, current_version):
        return None

    html_url = str(data.get("html_url") or "").strip()
    body = str(data.get("body") or "")
    asset = _find_launcher_asset(data)
    digest = str(asset.get("digest") or "")
    sha256 = ""
    if digest.startswith("sha256:"):
        sha256 = digest.split(":", 1)[1].lower()
    if not sha256:
        sha256 = _sha256_from_body(body, str(asset.get("name") or ""))
    if not re.fullmatch(r"[a-fA-F0-9]{64}", sha256):
        raise SelfUpdateError("Launcher update release is missing a SHA-256 hash for the EXE.")

    download_url = str(asset.get("browser_download_url") or "")
    if not download_url:
        raise SelfUpdateError("Launcher update release is missing an EXE download URL.")

    return LauncherUpdateInfo(
        tag_name=tag_name,
        html_url=html_url,
        asset_name=str(asset.get("name") or LAUNCHER_EXE_NAME),
        asset_size=int(asset.get("size") or 0),
        asset_sha256=sha256.lower(),
        download_url=download_url,
    )


def download_launcher_update(
    update: LauncherUpdateInfo,
    progress: callable | None = None,
    session: requests.Session | None = None,
    cancel_check: callable | None = None,
) -> Path:
    target_dir = downloads_dir() / "launcher-updates" / _safe_tag(update.tag_name)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / LAUNCHER_EXE_NAME
    return download_with_resume(
        update.download_url,
        target,
        update.asset_sha256,
        expected_size=update.asset_size,
        session=session,
        progress=progress,
        cancel_check=cancel_check,
        hash_error=SelfUpdateError("Launcher update SHA-256 did not match. Nothing was replaced."),
    )


def prepare_self_update(
    downloaded_exe: Path,
    *,
    expected_sha256: str | None = None,
    current_exe: Path | None = None,
    current_pid: int | None = None,
    popen: callable = subprocess.Popen,
) -> Path:
    current = current_exe or Path(sys.executable)
    if not current.is_file():
        raise SelfUpdateError(f"Current launcher EXE was not found: {current}")
    if not downloaded_exe.is_file():
        raise SelfUpdateError(f"Downloaded launcher update was not found: {downloaded_exe}")

    updater_dir = app_data_dir() / "updater"
    updater_dir.mkdir(parents=True, exist_ok=True)
    updater_exe = updater_dir / "SnowbreakLauncherUpdater.exe"
    shutil.copy2(current, updater_exe)

    command = [
        str(updater_exe),
        "--apply-update",
        "--update-source",
        str(downloaded_exe),
        "--update-target",
        str(current),
        "--update-pid",
        str(current_pid or os.getpid()),
    ]
    if expected_sha256:
        command.extend(["--update-sha256", expected_sha256])
    popen(command, close_fds=True)
    append_log(f"Started launcher self-update helper for {downloaded_exe}")
    return updater_exe


def apply_self_update(
    source: Path,
    target: Path,
    *,
    expected_sha256: str | None = None,
    old_pid: int | None = None,
    restart: bool = True,
    wait_seconds: float = 20.0,
    popen: callable = subprocess.Popen,
) -> int:
    deadline = time.monotonic() + wait_seconds
    if old_pid:
        _wait_for_process_exit(old_pid, deadline)

    target_temp = target.with_name(target.name + ".new")
    try:
        target_temp.unlink(missing_ok=True)
    except OSError:
        pass

    last_error: Exception | None = None
    try:
        if expected_sha256 and _file_sha256(source).lower() != expected_sha256.lower():
            _write_update_log("Downloaded launcher hash changed before replacement.")
            _cleanup_file(source)
            _cleanup_parent_if_empty(source)
            return 1
        shutil.copy2(source, target_temp)
        if expected_sha256 and _file_sha256(target_temp).lower() != expected_sha256.lower():
            _write_update_log("Copied launcher update hash did not match.")
            _cleanup_file(target_temp)
            _cleanup_file(source)
            _cleanup_parent_if_empty(source)
            return 1
    except OSError as exc:
        _write_update_log(f"Failed to prepare launcher replacement: {exc}")
        _cleanup_file(target_temp)
        _cleanup_file(source)
        _cleanup_parent_if_empty(source)
        return 1

    while time.monotonic() < deadline:
        try:
            os.replace(target_temp, target)
            last_error = None
            break
        except OSError as exc:
            last_error = exc
            time.sleep(0.35)
    if last_error is not None:
        _write_update_log(f"Failed to replace launcher: {last_error}")
        _cleanup_file(target_temp)
        _cleanup_file(source)
        _cleanup_parent_if_empty(source)
        return 1

    _cleanup_file(source)
    _cleanup_parent_if_empty(source)
    _cleanup_updater_dir()

    if restart:
        try:
            popen([str(target)], close_fds=True)
        except OSError as exc:
            _write_update_log(f"Updated launcher, but restart failed: {exc}")
            return 1
    return 0


def apply_self_update_from_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--apply-update", action="store_true")
    parser.add_argument("--update-source")
    parser.add_argument("--update-target")
    parser.add_argument("--update-pid")
    parser.add_argument("--update-sha256")
    args, _ = parser.parse_known_args(argv)
    if not args.apply_update or not args.update_source or not args.update_target:
        _write_update_log("Updater mode was called without source and target paths.")
        return 2
    old_pid = _parse_pid(args.update_pid)
    return apply_self_update(
        Path(args.update_source),
        Path(args.update_target),
        expected_sha256=args.update_sha256,
        old_pid=old_pid,
        restart=True,
    )


def _find_launcher_asset(data: dict) -> dict:
    assets = list(data.get("assets") or [])
    for asset in assets:
        if str(asset.get("name") or "").lower() == LAUNCHER_EXE_NAME.lower():
            return asset
    for asset in assets:
        name = str(asset.get("name") or "")
        lowered = name.lower()
        if lowered.startswith(LAUNCHER_EXE_NAME.lower().removesuffix(".exe")) and lowered.endswith(".exe"):
            return asset
    raise SelfUpdateError("Launcher update release did not contain an EXE asset.")


def _sha256_from_body(body: str, asset_name: str) -> str:
    if asset_name:
        asset_match = re.search(
            re.escape(asset_name) + r".{0,400}?([a-fA-F0-9]{64})",
            body,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if asset_match:
            return asset_match.group(1).lower()
    generic_match = re.search(r"SHA-?\s*256\s*:?\s*`?\s*([a-fA-F0-9]{64})", body, flags=re.IGNORECASE)
    return generic_match.group(1).lower() if generic_match else ""


def _version_tuple(value: str) -> tuple[int, ...] | None:
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)", value.strip(), flags=re.IGNORECASE)
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _safe_tag(tag_name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in tag_name)


def _parse_pid(value: str | None) -> int | None:
    if not value:
        return None
    try:
        pid = int(value)
    except ValueError:
        return None
    return pid if pid > 0 else None


def _wait_for_process_exit(pid: int, deadline: float) -> None:
    while time.monotonic() < deadline and _process_is_alive(pid):
        time.sleep(0.2)


def _process_is_alive(pid: int) -> bool:
    if pid == os.getpid():
        return False
    if os.name == "nt":
        synchronize = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            wait_timeout = 0x00000102
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == wait_timeout
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _write_update_log(message: str) -> None:
    try:
        path = app_data_dir() / "self-update.log"
        path.write_text(message + "\n", encoding="utf-8")
    except OSError:
        pass


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cleanup_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _cleanup_parent_if_empty(path: Path) -> None:
    parent = path.parent
    for _ in range(4):
        try:
            parent.rmdir()
        except OSError:
            break
        if parent.name.lower() == "downloads":
            break
        parent = parent.parent


def _cleanup_updater_dir() -> None:
    try:
        shutil.rmtree(app_data_dir() / "updater")
    except OSError:
        pass
