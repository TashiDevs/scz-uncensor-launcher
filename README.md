# Snowbreak Uncensor Launcher

A small Windows launcher for installing and updating Snowbreak: Containment Zone uncensor files.

It detects your Snowbreak install, sets the hidden localization switch, manages the `Game\Content\Paks\~ix` mod folder, downloads the current uncensor files, and can launch the game afterward.

## Download

Download the latest `SnowbreakUncensorLauncher.exe` from the GitHub Releases page and run it.

Windows may warn about the EXE because it is a fresh unsigned community build. The launcher does not need administrator rights.

## What It Changes

The launcher only touches:

- `localization.txt`
- `Game\Content\Paks\~ix`

It does not edit other game folders or other mod folders.

## Run From Source

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m snowbreak_launcher
```

## Build EXE

```powershell
.\build_exe.ps1
```

The EXE is created at:

```text
dist\SnowbreakUncensorLauncher.exe
```

## License

GPL-3.0. See `LICENSE`.
