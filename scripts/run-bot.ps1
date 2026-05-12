param(
    [string]$Token = $env:TOKEN,
    [string]$DataDir = "$PSScriptRoot\..\data",
    [string]$PythonExe = $env:BOT_PYTHON,
    [switch]$UseLocalDeps
)

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$botRoot = Join-Path $repoRoot "bot"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$dependencyPaths = @(
    (Join-Path $repoRoot ".bot_runtime_deps"),
    (Join-Path $repoRoot ".bot_deps")
)

if (-not $Token) {
    throw "TOKEN environment variable or -Token argument is required."
}

$resolvedDataDir = Resolve-Path $DataDir -ErrorAction SilentlyContinue
if ($resolvedDataDir) {
    $env:BOT_DATA_DIR = $resolvedDataDir.Path
} else {
    $env:BOT_DATA_DIR = $DataDir
}

function Add-LocalDependencyPaths {
    foreach ($dependencyPath in $dependencyPaths) {
        $depsDir = Resolve-Path $dependencyPath -ErrorAction SilentlyContinue
        if ($depsDir) {
            if ($env:PYTHONPATH) {
                $env:PYTHONPATH = "$($depsDir.Path);$($env:PYTHONPATH)"
            } else {
                $env:PYTHONPATH = $depsDir.Path
            }
        }
    }
}

New-Item -ItemType Directory -Force -Path $env:BOT_DATA_DIR | Out-Null

$env:TOKEN = $Token

Set-Location $botRoot

if (-not $PythonExe) {
    if (Test-Path $venvPython) {
        $PythonExe = $venvPython
    }
}

if (-not $PythonExe) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $PythonExe = $pythonCommand.Source
    }
}

if (-not $PythonExe) {
    $bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $bundledPython) {
        $PythonExe = $bundledPython
    }
}

if (-not $PythonExe) {
    throw "Python executable was not found. Set BOT_PYTHON or pass -PythonExe."
}

if ($UseLocalDeps -or ($PythonExe -eq $venvPython)) {
    Add-LocalDependencyPaths
}

& $PythonExe main.py
