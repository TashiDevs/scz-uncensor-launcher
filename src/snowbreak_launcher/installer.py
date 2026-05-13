from __future__ import annotations

import shutil
from pathlib import Path

from .config import append_log, downloads_dir, save_state
from .constants import MANAGED_FOLDER_NAME, STATIC_ASSET_NAMES
from .detection import validate_ix_folder
from .github_client import download_asset, fetch_latest_release, file_sha256
from .localization import ensure_localization_enabled
from .models import InstallInfo, LauncherState
from .progress import ProgressEvent, WeightedProgress
from .static_assets import configured_static_download, download_static_zip, import_static_zip


def setup_or_update(
    install: InstallInfo,
    state: LauncherState,
    progress: callable | None = None,
    cancel_check: callable | None = None,
    install_static_pack: bool = True,
) -> LauncherState:
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

    total_steps = 5 + len(release.assets) + (2 if static_config else 0)
    step = 0

    reporter.step("Prepare", "Preparing Snowbreak folders...", step, total_steps)
    if not install.paks_root.exists():
        raise FileNotFoundError(f"Paks folder does not exist: {install.paks_root}")
    validate_ix_folder(install.paks_root, install.ix_folder)
    install.ix_folder.mkdir(parents=True, exist_ok=True)
    step += 1

    reporter.step("Switch", "Enabling localization switch...", step, total_steps)
    append_log(ensure_localization_enabled(install.localization_path))
    step += 1

    reporter.step("Download", f"Preparing {release.tag_name}...", step, total_steps)
    staging = _fresh_staging_dir(release.tag_name)
    step += 1

    for asset in release.assets:
        reporter.step("Download", f"Downloading {asset.name}...", step, total_steps, current_file=asset.name)
        download_asset(asset, staging / asset.name, progress=_download_progress(reporter, step, total_steps))
        step += 1

    reporter.step("Install", "Cleaning ~ix and preserving static assets...", step, total_steps)
    clean_managed_folder(install.ix_folder)
    step += 1

    reporter.step("Install", "Installing verified uncensor files...", step, total_steps)
    installed_files: dict[str, str] = {}
    for asset in release.assets:
        reporter.check_cancelled()
        source = staging / asset.name
        target = install.ix_folder / asset.name
        shutil.copy2(source, target)
        installed_files[asset.name] = file_sha256(target)
        append_log(f"Installed {asset.name}")
    step += 1

    if static_config:
        url, expected_hash = static_config
        reporter.step("Download", "Downloading static asset pack...", step, total_steps)
        zip_path = download_static_zip(
            url,
            expected_hash,
            progress=_static_download_progress(reporter, step, total_steps),
        )
        step += 1

        reporter.step("Extract", "Extracting static asset pack...", step, total_steps)
        import_static_zip(zip_path, install.ix_folder)
        step += 1

    state.installed_release = release.tag_name
    state.installed_files = installed_files
    save_state(state)
    reporter.step("Done", f"Installed {release.tag_name}.", total_steps, total_steps)
    return state


def clean_managed_folder(ix_folder: Path) -> list[Path]:
    _validate_managed_folder_name(ix_folder)
    removed: list[Path] = []
    ix_folder.mkdir(parents=True, exist_ok=True)

    for item in ix_folder.iterdir():
        if item.is_file() and item.name in STATIC_ASSET_NAMES:
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
    save_state(state)
    return removed


def static_asset_status(ix_folder: Path) -> tuple[bool, list[str]]:
    present = [name for name in sorted(STATIC_ASSET_NAMES) if (ix_folder / name).is_file()]
    return len(present) == len(STATIC_ASSET_NAMES), present


def uncensor_file_status(ix_folder: Path, state: LauncherState) -> tuple[bool, list[str]]:
    if not state.installed_release or not state.installed_files:
        return False, []
    present = [name for name in sorted(state.installed_files) if (ix_folder / name).is_file()]
    return len(present) == len(state.installed_files), present


def _fresh_staging_dir(tag_name: str) -> Path:
    safe_tag = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in tag_name)
    staging = downloads_dir() / safe_tag
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    return staging


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
