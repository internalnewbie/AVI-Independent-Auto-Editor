@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title AVI Auto Editor - One Click Installer

echo ================================================
echo AVI AUTO EDITOR 0.3.4 - CHI MOT NUT CAI DAT
echo ================================================
echo Kiem tra cai dat cu, bo qua neu da co san.
echo.
rem Old setup launchers were kept in previous builds; archive them safely.
set "OLD_BATS=CAI_AI_CPU.bat CAI_CPU_ONLY.bat CAI_QWEN_MODEL.bat CAI_TU_DONG.bat KIEM_TRA_GPU.bat KIEM_TRA_TONG_THE.bat SUA_LOI_PIP_V03.bat TAO_CSV_NHAN.bat TAO_SETUP_EXE.bat"
for %%F in (%OLD_BATS%) do (
    if exist "%~dp0%%F" (
        if not exist "%~dp0_legacy_installers" mkdir "%~dp0_legacy_installers"
        move /Y "%~dp0%%F" "%~dp0_legacy_installers\%%F" >nul
    )
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_bootstrap.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" (
  echo CAI DAT LOI. Xem logs\setup_all_latest.log
  echo Neu loi Python xem logs\bootstrap_latest.log
) else (
  echo HOAN THANH. Mo CHAY_AUTO_EDIT.bat de su dung.
)
pause
exit /b %RESULT%
