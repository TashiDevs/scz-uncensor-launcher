from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path

from .constants import APP_DATA_DIR_NAME
from .models import InstallInfo, LauncherState


KEEP_APP_DATA_FILES = {"state.json", "launcher.log", "self-update.log"}


def app_data_dir() -> Path:
    candidates: list[Path] = []
    root = os.environ.get("LOCALAPPDATA")
    if root:
        candidates.append(Path(root) / APP_DATA_DIR_NAME)
    candidates.append(Path.home() / "AppData" / "Local" / APP_DATA_DIR_NAME)
    candidates.append(Path.cwd() / ".snowbreak_launcher")

    last_error: OSError | None = None
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return path
        except OSError as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise OSError("Could not create an app data folder.")


def state_path() -> Path:
    return app_data_dir() / "state.json"


def log_path() -> Path:
    return app_data_dir() / "launcher.log"


def downloads_dir() -> Path:
    path = app_data_dir() / "downloads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup_app_data() -> list[Path]:
    """Remove cached downloads while keeping only settings and logs."""
    root = app_data_dir()
    removed: list[Path] = []
    for item in root.iterdir():
        if item.is_file() and item.name in KEEP_APP_DATA_FILES:
            continue
        try:
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink(missing_ok=True)
            removed.append(item)
        except OSError:
            # A running updater helper can stay locked briefly; the next startup
            # will try again.
            continue
    return removed


def load_state() -> LauncherState:
    path = state_path()
    if not path.exists():
        return LauncherState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return LauncherState()
    state = LauncherState()
    for key, value in data.items():
        if hasattr(state, key):
            setattr(state, key, value)
    if not isinstance(state.installed_files, dict):
        state.installed_files = {}
    if not isinstance(state.static_asset_pack, dict):
        state.static_asset_pack = {}
    return state


def save_state(state: LauncherState) -> None:
    state_path().write_text(
        json.dumps(asdict(state), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def install_to_state(install: InstallInfo, state: LauncherState) -> LauncherState:
    state.install_type = install.install_type
    state.game_root = str(install.game_root)
    state.paks_root = str(install.paks_root)
    state.ix_folder = str(install.ix_folder)
    state.localization_path = str(install.localization_path)
    state.launcher_exe = str(install.launcher_exe) if install.launcher_exe else None
    return state


def state_to_install(state: LauncherState) -> InstallInfo | None:
    required = (state.install_type, state.game_root, state.paks_root, state.ix_folder, state.localization_path)
    if not all(required):
        return None

    game_root = Path(str(state.game_root))
    paks_root = Path(str(state.paks_root))
    ix_folder = Path(str(state.ix_folder))
    localization_path = Path(str(state.localization_path))

    if not game_root.exists() or not paks_root.exists():
        return None

    return InstallInfo(
        install_type=str(state.install_type),
        game_root=game_root,
        paks_root=paks_root,
        ix_folder=ix_folder,
        localization_path=localization_path,
        launcher_exe=Path(state.launcher_exe) if state.launcher_exe else None,
    )


def append_log(message: str) -> None:
    from datetime import datetime

    line = f"{datetime.now().isoformat(timespec='seconds')} {message}\n"
    with log_path().open("a", encoding="utf-8") as handle:
        handle.write(line)


def load_env_file(root: Path | None = None) -> None:
    env_path = (root or Path.cwd()) / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
