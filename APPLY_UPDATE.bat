@echo off
setlocal
cd /d "%~dp0"
py APPLY_UPDATE.py %*
if errorlevel 1 (
  echo.
  echo Update failed. Review the message above.
  pause
  exit /b 1
)
echo.
echo Update applied. Run your normal START_LOCAL.bat from the project folder.
pause
