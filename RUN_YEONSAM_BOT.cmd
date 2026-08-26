@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title Yeonsam Bot Launcher

echo [launcher] Using the current launcher from:
echo [launcher] %~dp0
call "%~dp0start-bot.bat"
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
