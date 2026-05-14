from __future__ import annotations

from dataclasses import dataclass

from .models import GitHubRelease, InstallInfo, LauncherState


@dataclass(frozen=True)
class UpdateDecision:
    ui_state: str
    action_label: str
    reason: str
    should_auto_update: bool = False
    local_install_complete: bool = False


def decide_next_state(
    state: LauncherState,
    install: InstallInfo | None,
    latest_release: GitHubRelease | None,
    core_files_installed: bool,
    static_assets_installed: bool,
) -> UpdateDecision:
    if install is None:
        return UpdateDecision("ready_to_install", "Choose Folder", "Choose Snowbreak folder.")

    if not state.installed_release:
        return UpdateDecision("ready_to_install", "Install", "Ready to install.")

    if not core_files_installed and not static_assets_installed:
        return UpdateDecision("ready_to_install", "Install", "Uncensor files and assets are missing.")

    if not core_files_installed:
        return UpdateDecision("ready_to_install", "Install", "Uncensor files are missing.")

    if not static_assets_installed:
        return UpdateDecision("ready_to_install", "Install", "Static assets missing.")

    if latest_release and state.installed_release != latest_release.tag_name:
        return UpdateDecision(
            "ready_to_update",
            "Update",
            f"Update available: {latest_release.tag_name}",
            should_auto_update=state.auto_update_enabled,
            local_install_complete=True,
        )

    return UpdateDecision("ready_to_launch", "Launch", "Done.", local_install_complete=True)
