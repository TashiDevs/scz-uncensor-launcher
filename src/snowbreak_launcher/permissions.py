from __future__ import annotations

import ctypes
import os
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


def _quote_arg(value: str) -> str:
    escaped = value.replace('"', r"\"")
    return f'"{escaped}"' if any(ch.isspace() for ch in escaped) else escaped
