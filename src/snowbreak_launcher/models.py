from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class InstallInfo:
    install_type: str
    game_root: Path
    paks_root: Path
    ix_folder: Path
    localization_path: Path
    launcher_exe: Path | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GitHubAsset:
    name: str
    size: int
    sha256: str
    download_url: str


@dataclass(frozen=True)
class GitHubRelease:
    tag_name: str
    html_url: str
    assets: tuple[GitHubAsset, ...]


@dataclass
class LauncherState:
    accepted_notice: bool = False
    disclaimer_accepted_at: str | None = None
    auto_update_enabled: bool = False
    install_type: str | None = None
    game_root: str | None = None
    paks_root: str | None = None
    ix_folder: str | None = None
    localization_path: str | None = None
    launcher_exe: str | None = None
    last_checked_release: str | None = None
    last_check_time: str | None = None
    installed_release: str | None = None
    installed_files: dict[str, str] = field(default_factory=dict)
