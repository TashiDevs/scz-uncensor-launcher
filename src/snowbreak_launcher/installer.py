from __future__ import annotations

import shutil
from pathlib import Path

from .config import append_log, downloads_dir, save_state
from .constants import MANAGED_FOLDER_NAME, STATIC_ASSET_NAMES
from .detection import validate_ix_folder
from .github_client import ReleaseError, download_asset, fetch_latest_release, file_sha256
from .localization import ensure_localization_enabled
from .models import GitHubAsset, GitHubRelease, InstallInfo, LauncherState
from .progress import ProgressEvent, WeightedProgress
from .static_assets import configured_static_download, download_static_zip, import_static_zip, remember_static_pack, static_pack_is_current


def setup_or_update(
    install: InstallInfo,
    state: LauncherState,
    progress: callable | None = None,
    cancel_check: callable | None = None,
    install_static_pack: bool = True,
) -> LauncherState:
    staging: Path | None = None
    zip_path: Path | None = None
    try:
        reporter = WeightedProgress(progress, cancel_check)
        _progress(progress, "Checking latest uncensor release...", 0.02)
        reporter.check_cancelled()
        release = fetch_latest_release()

        static_config = configured_static_download() if install_static_pack else None
        if install_static_pack and static_config is None:
            raise RuntimeError(
                "The static asset direct download is not configured yet. "
                "Check SBUL_STATIC_ASSET_URL and SBUL_STATIC_ASSET_SHA256 in .env, or import the ZIP manually."
            )

        if not install.paks_root.exists():
            raise FileNotFoundError(f"Paks folder does not exist: {install.paks_root}")
        validate_ix_folder(install.paks_root, install.ix_folder)
        install.ix_folder.mkdir(parents=True, exist_ok=True)
        reporter.check_cancelled()

        assets_to_download, current_core_hashes = core_assets_needing_download(install.ix_folder, release)

        static_pack_current = False
        if static_config:
            static_pack_current = static_pack_is_current(install.ix_folder, state, *static_config)
        total_steps = 5 + len(assets_to_download) + (0 if static_pack_current else 2 if static_config else 0)
        step = 0

        reporter.step("Prepare", "Preparing Snowbreak folders...", step, total_steps)
        step += 1

        reporter.step("Switch", "Enabling localization switch...", step, total_steps)
        append_log(ensure_localization_enabled(install.localization_path))
        step += 1

        if assets_to_download:
            download_names = ", ".join(asset.name for asset in assets_to_download)
            reporter.step("Download", f"Preparing changed uncensor files: {download_names}", step, total_steps)
            staging = _fresh_staging_dir(release.tag_name)
        else:
            reporter.step("Download", "Uncensor files are already current.", step, total_steps)
            append_log("Uncensor files already current; skipping GitHub downloads.")
        step += 1

        for asset in assets_to_download:
            if staging is None:
                raise RuntimeError("Download staging folder was not prepared.")
            reporter.step("Download", f"Downloading {asset.name}...", step, total_steps, current_file=asset.name)
            download_asset(
                asset,
                staging / asset.name,
                progress=_download_progress(reporter, step, total_steps),
                cancel_check=cancel_check,
            )
            step += 1

        current_asset_names = {asset.name for asset in release.assets}
        reporter.step("Install", "Cleaning old uncensor files...", step, total_steps)
        clean_managed_folder(install.ix_folder, preserve_names=current_asset_names)
        step += 1

        reporter.step("Install", "Installing changed uncensor files...", step, total_steps)
        installed_files: dict[str, str] = dict(current_core_hashes)
        downloaded_names = {asset.name for asset in assets_to_download}
        for asset in assets_to_download:
            reporter.check_cancelled()
            if staging is None:
                raise RuntimeError("Download staging folder was not prepared.")
            source = staging / asset.name
            target = install.ix_folder / asset.name
            shutil.copy2(source, target)
            actual_hash = file_sha256(target).lower()
            if actual_hash != asset.sha256.lower():
                raise ReleaseError(f"SHA-256 mismatch after installing {asset.name}.")
            installed_files[asset.name] = actual_hash
            append_log(f"Installed {asset.name}")

        for asset in release.assets:
            if asset.name in downloaded_names:
                continue
            target = install.ix_folder / asset.name
            if asset.name not in installed_files:
                actual_hash = file_sha256(target).lower()
                if actual_hash != asset.sha256.lower():
                    raise ReleaseError(f"SHA-256 mismatch for existing uncensor file: {asset.name}")
                installed_files[asset.name] = actual_hash
            append_log(f"Kept current uncensor file: {asset.name}")
        step += 1

        if static_config and static_pack_current:
            url, expected_hash = static_config
            remember_static_pack(install.ix_folder, state, url, expected_hash)
            append_log("Static asset pack already installed; skipping download.")
        elif static_config:
            url, expected_hash = static_config
            reporter.step("Download", "Downloading static asset pack...", step, total_steps)
            zip_path = download_static_zip(
                url,
                expected_hash,
                progress=_static_download_progress(reporter, step, total_steps),
                cancel_check=cancel_check,
            )
            step += 1

            reporter.step("Extract", "Extracting static asset pack...", step, total_steps)
            import_static_zip(zip_path, install.ix_folder)
            remember_static_pack(install.ix_folder, state, url, expected_hash)
            step += 1

        state.installed_release = release.tag_name
        state.installed_files = installed_files
        save_state(state)
        reporter.step("Done", f"Installed {release.tag_name}.", total_steps, total_steps)
        return state
    finally:
        _cleanup_path(staging)
        _cleanup_path(zip_path)


def clean_managed_folder(ix_folder: Path, preserve_names: set[str] | None = None) -> list[Path]:
    _validate_managed_folder_name(ix_folder)
    removed: list[Path] = []
    ix_folder.mkdir(parents=True, exist_ok=True)
    preserved = {name.lower() for name in STATIC_ASSET_NAMES}
    if preserve_names:
        preserved.update(name.lower() for name in preserve_names)

    for item in ix_folder.iterdir():
        if item.is_file() and item.name.lower() in preserved:
            continue
        removed.append(item)
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink(missing_ok=True)
        append_log(f"Removed from ~ix: {item.name}")
    return removed


def uninstall_github_files(install: InstallInfo, state: LauncherState) -> int:
    validate_ix_folder(install.paks_root, install.ix_folder)
    removed = 0
    for filename in list(state.installed_files):
        target = install.ix_folder / filename
        if target.exists() and target.is_file():
            target.unlink()
            removed += 1
            append_log(f"Uninstalled {filename}")
    state.installed_release = None
    state.installed_files = {}
    save_state(state)
    return removed


def uninstall_all_managed_files(install: InstallInfo, state: LauncherState) -> int:
    validate_ix_folder(install.paks_root, install.ix_folder)
    removed = 0
    install.ix_folder.mkdir(parents=True, exist_ok=True)
    for item in install.ix_folder.iterdir():
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink(missing_ok=True)
        removed += 1
        append_log(f"Uninstalled from ~ix: {item.name}")
    state.installed_release = None
    state.installed_files = {}
    state.static_asset_pack = {}
    save_state(state)
    return removed


def static_asset_status(ix_folder: Path) -> tuple[bool, list[str]]:
    present = [name for name in sorted(STATIC_ASSET_NAMES) if (ix_folder / name).is_file()]
    return len(present) == len(STATIC_ASSET_NAMES), present


def uncensor_file_status(ix_folder: Path, state: LauncherState) -> tuple[bool, list[str]]:
    if not state.installed_release or not state.installed_files:
        return False, []
    present = [
        name
        for name, expected_hash in sorted(state.installed_files.items())
        if _file_matches_hash(ix_folder / name, str(expected_hash))
    ]
    return len(present) == len(state.installed_files), present


def core_assets_needing_download(ix_folder: Path, release: GitHubRelease) -> tuple[list[GitHubAsset], dict[str, str]]:
    downloads: list[GitHubAsset] = []
    current_hashes: dict[str, str] = {}
    for asset in release.assets:
        target = ix_folder / asset.name
        if target.is_file():
            try:
                actual_hash = file_sha256(target).lower()
            except OSError:
                actual_hash = ""
            if actual_hash == asset.sha256.lower():
                current_hashes[asset.name] = actual_hash
                continue
        downloads.append(asset)
    return downloads, current_hashes


def _fresh_staging_dir(tag_name: str) -> Path:
    safe_tag = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in tag_name)
    staging = downloads_dir() / safe_tag
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    return staging


def _cleanup_path(path: Path | None) -> None:
    if path is None:
        return
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    except OSError:
        append_log(f"Could not clean temporary file: {path}")


def _download_progress(reporter: WeightedProgress, step: int, total_steps: int) -> callable:
    def report(name: str, downloaded: int, total: int) -> None:
        local = downloaded / total if total else 0.0
        reporter.step(
            "Download",
            f"Downloading {name}",
            step,
            total_steps,
            step_fraction=local,
            current_file=name,
            bytes_downloaded=downloaded,
            bytes_total=total,
        )

    return report


def _static_download_progress(reporter: WeightedProgress, step: int, total_steps: int) -> callable:
    def report(downloaded: int, total: int) -> None:
        local = downloaded / total if total else 0.0
        reporter.step(
            "Download",
            "Downloading static asset pack",
            step,
            total_steps,
            step_fraction=local,
            current_file="static-assets.zip",
            bytes_downloaded=downloaded,
            bytes_total=total,
        )

    return report


def _progress(progress: callable | None, message: str, fraction: float = 0.0) -> None:
    append_log(message)
    if progress:
        progress(ProgressEvent(phase="Check", message=message, fraction=fraction))


def _validate_managed_folder_name(ix_folder: Path) -> None:
    if ix_folder.name.lower() != MANAGED_FOLDER_NAME.lower() or ix_folder.parent.name.lower() != "paks":
        raise ValueError(f"Refusing to clean unexpected folder: {ix_folder}")


def _file_matches_hash(path: Path, expected_hash: str) -> bool:
    if not path.is_file() or not expected_hash:
        return False
    try:
        return file_sha256(path).lower() == expected_hash.lower()
    except OSError:
        return False
