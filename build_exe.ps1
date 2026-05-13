param(
    [switch]$UseUpx
)

$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}

$pyinstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--icon", "$PSScriptRoot\assets\images\app-icon.ico",
    "--add-data", "$PSScriptRoot\assets;assets",
    "--hidden-import", "snowbreak_launcher.app",
    "--exclude-module", "PySide6.Qt3DAnimation",
    "--exclude-module", "PySide6.Qt3DCore",
    "--exclude-module", "PySide6.Qt3DExtras",
    "--exclude-module", "PySide6.Qt3DInput",
    "--exclude-module", "PySide6.Qt3DLogic",
    "--exclude-module", "PySide6.Qt3DRender",
    "--exclude-module", "PySide6.QtCharts",
    "--exclude-module", "PySide6.QtDataVisualization",
    "--exclude-module", "PySide6.QtDesigner",
    "--exclude-module", "PySide6.QtGraphs",
    "--exclude-module", "PySide6.QtHelp",
    "--exclude-module", "PySide6.QtMultimedia",
    "--exclude-module", "PySide6.QtMultimediaWidgets",
    "--exclude-module", "PySide6.QtOpenGL",
    "--exclude-module", "PySide6.QtOpenGLWidgets",
    "--exclude-module", "PySide6.QtPdf",
    "--exclude-module", "PySide6.QtPdfWidgets",
    "--exclude-module", "PySide6.QtPositioning",
    "--exclude-module", "PySide6.QtQml",
    "--exclude-module", "PySide6.QtQuick",
    "--exclude-module", "PySide6.QtQuick3D",
    "--exclude-module", "PySide6.QtQuickControls2",
    "--exclude-module", "PySide6.QtQuickWidgets",
    "--exclude-module", "PySide6.QtRemoteObjects",
    "--exclude-module", "PySide6.QtScxml",
    "--exclude-module", "PySide6.QtSensors",
    "--exclude-module", "PySide6.QtSerialPort",
    "--exclude-module", "PySide6.QtSql",
    "--exclude-module", "PySide6.QtStateMachine",
    "--exclude-module", "PySide6.QtTest",
    "--exclude-module", "PySide6.QtTextToSpeech",
    "--exclude-module", "PySide6.QtUiTools",
    "--exclude-module", "PySide6.QtWebChannel",
    "--exclude-module", "PySide6.QtWebEngineCore",
    "--exclude-module", "PySide6.QtWebEngineQuick",
    "--exclude-module", "PySide6.QtWebEngineWidgets",
    "--exclude-module", "PySide6.QtWebSockets",
    "--exclude-module", "PySide6.QtXml",
    "--name", "SnowbreakUncensorLauncher",
    "--paths", "$PSScriptRoot\src",
    "$PSScriptRoot\src\snowbreak_launcher\__main__.py"
)

if ($UseUpx) {
    $upxDir = Join-Path $PSScriptRoot "tools\upx-5.1.0-win64"
    if (Test-Path -LiteralPath (Join-Path $upxDir "upx.exe")) {
        Write-Host "Using UPX: $upxDir"
        $pyinstallerArgs = @("-m", "PyInstaller", "--upx-dir", $upxDir) + $pyinstallerArgs[2..($pyinstallerArgs.Count - 1)]
    }
    else {
        Write-Warning "UPX was requested, but tools\upx-5.1.0-win64\upx.exe was not found. Building without UPX."
    }
}
else {
    Write-Host "Building without UPX. This is the recommended public release mode."
}

& $python @pyinstallerArgs

Write-Host ""
Write-Host "Build complete: dist\SnowbreakUncensorLauncher.exe"
