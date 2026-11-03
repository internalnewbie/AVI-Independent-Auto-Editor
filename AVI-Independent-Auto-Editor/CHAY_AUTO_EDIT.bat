@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" AVI_Auto_Editor.py
) else (
  echo Chua cai dat. Hay chay CAI_MOT_LAN.bat truoc.
  pause
  exit /b 1
)
if errorlevel 1 (
  echo.
  echo App gap loi. Xem logs va kiem tra AI packages.
  pause
)
