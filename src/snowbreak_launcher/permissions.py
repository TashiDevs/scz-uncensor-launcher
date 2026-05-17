from __future__ import annotations

import ctypes
import os
import stat
import sys
from pathlib import Path

from .models import InstallInfo


def is_running_as_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def is_path_in_protected_folder(path: Path) -> bool:
    candidate = _normalise_for_compare(path)
    for protected in _protected_roots():
        if candidate == protected or candidate.startswith(protected + "\\"):
            return True
    return False


def install_requires_admin(install: InstallInfo) -> bool:
    if is_running_as_admin():
        return False
    paths = (
        install.game_root,
        install.paks_root,
        install.ix_folder,
        install.localization_path.parent,
    )
    return any(is_path_in_protected_folder(path) for path in paths)


def clear_readonly_for_launcher_path(
    path: Path,
    *,
    ix_folder: Path | None = None,
    paks_root: Path | None = None,
    localization_parent: Path | None = None,
    localization_path: Path | None = None,
) -> None:
    clear_mode = _launcher_owned_clear_mode(
        path,
        ix_folder=ix_folder,
        paks_root=paks_root,
        localization_parent=localization_parent,
        localization_path=localization_path,
    )
    if clear_mode is None:
        raise ValueError(f"Refusing to change attributes outside launcher-owned paths: {path}")
    if not path.exists():
        return
    targets: list[Path] = []
    if clear_mode == "recursive" and path.is_dir() and not path.is_symlink():
        targets.extend(child for child in path.rglob("*") if not child.is_symlink())
    targets.append(path)
    for target in targets:
        try:
            target.chmod(target.stat().st_mode | stat.S_IWRITE | stat.S_IWUSR)
        except FileNotFoundError:
            continue


def relaunch_as_admin() -> bool:
    if os.name != "nt":
        return False
    executable = Path(sys.executable)
    if executable.suffix.lower() != ".exe":
        return False
    params = " ".join(_quote_arg(arg) for arg in sys.argv[1:])
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        str(executable),
        params,
        str(executable.parent),
        1,
    )
    return int(result) > 32


def _protected_roots() -> set[str]:
    roots: set[str] = set()
    for key in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        value = os.environ.get(key)
        if value:
            roots.add(_normalise_for_compare(Path(value)))
    return roots


def _normalise_for_compare(path: Path) -> str:
    return str(path).rstrip("\\/").replace("/", "\\").casefold()


def _launcher_owned_clear_mode(
    path: Path,
    *,
    ix_folder: Path | None,
    paks_root: Path | None,
    localization_parent: Path | None,
    localization_path: Path | None,
) -> str | None:
    candidate = _normalise_for_compare(path)
    if localization_path and candidate == _normalise_for_compare(localization_path):
        return "single"
    if localization_parent and candidate == _normalise_for_compare(localization_parent):
        return "single"
    if paks_root and candidate == _normalise_for_compare(paks_root):
        return "single"
    if ix_folder:
        ix = _normalise_for_compare(ix_folder)
        if candidate == ix or candidate.startswith(ix + "\\"):
            return "recursive"
    return None


def _quote_arg(value: str) -> str:
    escaped = value.replace('"', r"\"")
    return f'"{escaped}"' if any(ch.isspace() for ch in escaped) else escaped
