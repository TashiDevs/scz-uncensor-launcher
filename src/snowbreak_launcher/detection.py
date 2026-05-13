from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from .constants import MANAGED_FOLDER_NAME, OLD_BUILD_CUTOFF_ISO, PAKS_RELATIVE_PARTS, STEAM_APP_ID
from .models import InstallInfo


def auto_detect_install() -> InstallInfo | None:
    for candidate in (*_detect_steam_installs(), *_detect_standalone_installs()):
        return candidate
    return None


def resolve_manual_install(selected: str | Path) -> InstallInfo | None:
    path = Path(selected).expanduser()
    if not path.exists():
        return None

    for root, install_type, steam_common in _manual_root_candidates(path):
        info = build_install_info(root, install_type=install_type, steam_common=steam_common)
        if info and info.paks_root.exists():
            return info
    return None


def build_install_info(
    game_root: Path,
    install_type: str,
    steam_common: Path | None = None,
) -> InstallInfo | None:
    game_root = game_root.resolve()
    paks_root = _find_paks_root(game_root)
    if paks_root is None:
        paks_root = game_root.joinpath(*PAKS_RELATIVE_PARTS)

    if install_type == "Steam":
        localization_path = (steam_common or game_root.parent) / "localization.txt"
        launcher_exe = None
    else:
        localization_path = _choose_standalone_localization(game_root)
        launcher_exe = _find_standalone_launcher(game_root)

    warnings = tuple(_collect_warnings(game_root, paks_root, localization_path, install_type))
    return InstallInfo(
        install_type=install_type,
        game_root=game_root,
        paks_root=paks_root,
        ix_folder=paks_root / MANAGED_FOLDER_NAME,
        localization_path=localization_path,
        launcher_exe=launcher_exe,
        warnings=warnings,
    )


def validate_ix_folder(paks_root: Path, ix_folder: Path) -> None:
    paks_root = paks_root.resolve()
    ix_folder = ix_folder.resolve() if ix_folder.exists() else ix_folder.absolute()

    if paks_root.name.lower() != "paks":
        raise ValueError(f"Refusing to manage folder because this is not a Paks folder: {paks_root}")

    expected = paks_root / MANAGED_FOLDER_NAME
    if ix_folder != expected:
        raise ValueError(f"Refusing to manage unexpected folder: {ix_folder}")


def _detect_steam_installs() -> list[InstallInfo]:
    steam_roots = _steam_roots_from_registry()
    installs: list[InstallInfo] = []

    for steam_root in steam_roots:
        for library in _steam_libraries(steam_root):
            manifest = library / "steamapps" / f"appmanifest_{STEAM_APP_ID}.acf"
            if not manifest.exists():
                continue
            install_dir = _parse_vdf_value(manifest.read_text(encoding="utf-8", errors="ignore"), "installdir")
            game_root = library / "steamapps" / "common" / (install_dir or "SNOWBREAK")
            info = build_install_info(game_root, install_type="Steam", steam_common=library / "steamapps" / "common")
            if info and info.paks_root.exists():
                installs.append(info)
    return installs


def _detect_standalone_installs() -> list[InstallInfo]:
    installs: list[InstallInfo] = []
    seen: set[Path] = set()
    for root in _standalone_root_candidates():
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        info = build_install_info(resolved, install_type="Standalone")
        if info and info.paks_root.exists():
            installs.append(info)
    return installs


def _manual_root_candidates(path: Path) -> list[tuple[Path, str, Path | None]]:
    path = path.resolve()
    candidates: list[tuple[Path, str, Path | None]] = []

    if path.name.lower() == MANAGED_FOLDER_NAME.lower() and path.parent.name.lower() == "paks":
        root = _root_from_paks(path.parent)
        if root:
            candidates.append((root, _guess_install_type(root), _steam_common_for_game_root(root)))

    if path.name.lower() == "paks":
        root = _root_from_paks(path)
        if root:
            candidates.append((root, _guess_install_type(root), _steam_common_for_game_root(root)))

    if path.name.lower() == "common" and (path / "SNOWBREAK").exists():
        candidates.append((path / "SNOWBREAK", "Steam", path))

    if (path / f"appmanifest_{STEAM_APP_ID}.acf").exists() and path.parent.name.lower() == "steamapps":
        common = path.parent / "common"
        candidates.append((common / "SNOWBREAK", "Steam", common))

    candidates.append((path, _guess_install_type(path), _steam_common_for_game_root(path)))
    if (path / "SNOWBREAK").exists():
        candidates.append((path / "SNOWBREAK", "Steam", path))

    unique: list[tuple[Path, str, Path | None]] = []
    seen: set[tuple[Path, str]] = set()
    for root, install_type, steam_common in candidates:
        key = (root, install_type)
        if key not in seen:
            seen.add(key)
            unique.append((root, install_type, steam_common))
    return unique


def _root_from_paks(paks_root: Path) -> Path | None:
    parts = [part.lower() for part in paks_root.parts]
    tail = [part.lower() for part in PAKS_RELATIVE_PARTS]
    if len(parts) >= 3 and parts[-3:] == tail:
        return paks_root.parents[2]
    return None


def _find_paks_root(game_root: Path) -> Path | None:
    for game_name in ("Game", "game"):
        candidate = game_root / game_name / "Content" / "Paks"
        if candidate.exists():
            return candidate
    return None


def _choose_standalone_localization(game_root: Path) -> Path:
    candidates = [
        game_root / "localization.txt",
        game_root / "Game" / "cbjq" / "localization.txt",
        game_root / "game" / "cbjq" / "localization.txt",
        game_root / "cbjq" / "localization.txt",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    for candidate in candidates[1:]:
        if candidate.parent.exists():
            return candidate
    return candidates[0]


def _find_standalone_launcher(game_root: Path) -> Path | None:
    names = (
        "SnowbreakLauncher.exe",
        "Snowbreak.exe",
        "SeasunLauncher.exe",
        "launcher.exe",
        "Launcher.exe",
    )
    for name in names:
        candidate = game_root / name
        if candidate.exists():
            return candidate

    try:
        for candidate in game_root.glob("*.exe"):
            lowered = candidate.name.lower()
            if "launcher" in lowered or "snowbreak" in lowered:
                return candidate
    except OSError:
        return None
    return None


def _collect_warnings(
    game_root: Path,
    paks_root: Path,
    localization_path: Path,
    install_type: str,
) -> list[str]:
    warnings: list[str] = []
    if not paks_root.exists():
        warnings.append("The Paks folder was not found. Please double-check that this is the real Snowbreak install.")
    if not localization_path.exists():
        warnings.append("localization.txt was not found. The launcher will create it in the expected location.")
    if install_type == "Standalone" and _find_standalone_launcher(game_root) is None:
        warnings.append("No obvious standalone launcher EXE was found. Launch may need a manual EXE selection.")

    cutoff = datetime.fromisoformat(OLD_BUILD_CUTOFF_ISO)
    dated_files = [
        game_root / "manifest.json",
        game_root / "version.cfg",
        game_root / "Game" / "manifest.json",
        game_root / "game" / "manifest.json",
    ]
    for candidate in dated_files:
        if candidate.exists():
            modified = datetime.fromtimestamp(candidate.stat().st_mtime)
            if modified < cutoff:
                warnings.append(
                    "This install has files older than May 2026. If modding fails, update Snowbreak first."
                )
            break
    return warnings


def _guess_install_type(path: Path) -> str:
    text = str(path).lower()
    if "steamapps" in text:
        return "Steam"
    return "Standalone"


def _steam_common_for_game_root(path: Path) -> Path | None:
    parts = [part.lower() for part in path.parts]
    if "steamapps" not in parts:
        return None
    try:
        index = parts.index("common")
    except ValueError:
        return None
    return Path(*path.parts[: index + 1])


def _steam_roots_from_registry() -> list[Path]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []

    keys = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam"),
    ]
    roots: list[Path] = []
    for hive, subkey in keys:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                for value_name in ("SteamPath", "InstallPath"):
                    try:
                        value, _ = winreg.QueryValueEx(key, value_name)
                    except OSError:
                        continue
                    path = Path(str(value))
                    if path.exists():
                        roots.append(path)
        except OSError:
            continue
    return _unique_paths(roots)


def _steam_libraries(steam_root: Path) -> list[Path]:
    libraries = [steam_root]
    library_file = steam_root / "steamapps" / "libraryfolders.vdf"
    if library_file.exists():
        text = library_file.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            libraries.append(Path(match.group(1).replace("\\\\", "\\")))
    return _unique_paths([path for path in libraries if path.exists()])


def _standalone_root_candidates() -> list[Path]:
    candidates: list[Path] = []
    candidates.extend(_standalone_registry_locations())

    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(env_name)
        if not base:
            continue
        for child in ("Snowbreak", "SNOWBREAK", "Seasun\\Snowbreak"):
            candidates.append(Path(base) / child)

    for drive in ("C:", "D:", "E:"):
        candidates.extend(
            [
                Path(drive) / "Snowbreak",
                Path(drive) / "SNOWBREAK",
                Path(drive) / "Seasun" / "Snowbreak",
            ]
        )
    return [path for path in _unique_paths(candidates) if path.exists()]


def _standalone_registry_locations() -> list[Path]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []

    uninstall_roots = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    locations: list[Path] = []
    for hive, root in uninstall_roots:
        try:
            with winreg.OpenKey(hive, root) as key:
                for index in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(key, index)
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            name = _query_registry_string(winreg, subkey, "DisplayName")
                            location = _query_registry_string(winreg, subkey, "InstallLocation")
                    except OSError:
                        continue
                    haystack = f"{name} {location}".lower()
                    if "snowbreak" in haystack or "containment zone" in haystack or "seasun" in haystack:
                        if location:
                            locations.append(Path(location))
        except OSError:
            continue
    return locations


def _query_registry_string(winreg_module, key, value_name: str) -> str:
    try:
        value, _ = winreg_module.QueryValueEx(key, value_name)
    except OSError:
        return ""
    return str(value)


def _parse_vdf_value(text: str, key: str) -> str | None:
    match = re.search(rf'"{re.escape(key)}"\s+"([^"]+)"', text)
    if not match:
        return None
    return match.group(1)


def _unique_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique
