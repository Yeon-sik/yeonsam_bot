@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0"
title Yeonsam Bot Launcher

set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo [launcher] Preparing the Python virtual environment...
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv "%~dp0.venv"
    ) else (
        where python >nul 2>&1
        if errorlevel 1 goto :python_missing
        python -m venv "%~dp0.venv"
    )
)
if not exist "%PYTHON%" goto :venv_failed

if not exist "%~dp0scripts\local_launcher.py" goto :launcher_missing
"%PYTHON%" "%~dp0scripts\local_launcher.py"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo [launcher] The launcher stopped with exit code %EXIT_CODE%.
    echo [launcher] Check the error above and press any key to close.
    pause
)
popd
endlocal & exit /b %EXIT_CODE%

:python_missing
echo [launcher] Python 3.11 or later was not found.
set "EXIT_CODE=1"
goto :finish_error

:venv_failed
echo [launcher] The Python virtual environment could not be created.
set "EXIT_CODE=1"
goto :finish_error

:launcher_missing
echo [launcher] scripts\local_launcher.py was not found.
set "EXIT_CODE=1"

:finish_error
echo [launcher] Check the repository folder and press any key to close.
pause
popd
endlocal & exit /b %EXIT_CODE%
