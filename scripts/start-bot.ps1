$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$launcher = Join-Path $repoRoot "scripts\local_launcher.py"
$venvRoot = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    $bootstrapArgs = @()
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
        if ($pythonCommand) {
            $bootstrapArgs = @("-3")
        }
    }
    if (-not $pythonCommand) {
        throw "Python was not found. Install Python 3.11 or later."
    }
    Write-Host "Preparing the Python virtual environment for the first run..."
    & $pythonCommand.Source @bootstrapArgs -m venv $venvRoot
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
        throw "The Python virtual environment could not be created. Check the Python installation."
    }
}

& $venvPython $launcher
if ($LASTEXITCODE -ne 0) {
    throw "The local launcher exited with code $LASTEXITCODE."
}
