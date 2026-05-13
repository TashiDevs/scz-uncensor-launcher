from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .constants import STEAM_APP_ID
from .models import InstallInfo


def launch_game(install: InstallInfo, chosen_exe: Path | None = None) -> None:
    if install.install_type == "Steam":
        os.startfile(f"steam://rungameid/{STEAM_APP_ID}")  # type: ignore[attr-defined]
        return

    exe = chosen_exe or install.launcher_exe
    if not exe or not exe.exists():
        raise FileNotFoundError("No standalone launcher EXE was selected.")
    subprocess.Popen([str(exe)], cwd=str(exe.parent))
