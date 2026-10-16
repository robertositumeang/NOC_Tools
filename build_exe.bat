@echo off
setlocal EnableDelayedExpansion

echo.
echo  ============================================================
echo   NOC Tools - Build Executable
echo   PT. KEREAKTIF Indonesia
echo  ============================================================
echo.

set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

:: Cari file Site Management
set "MASTER_FILE="
for /f "usebackq delims=" %%F in (`powershell -NoProfile -Command "$files=Get-ChildItem -File -Filter 'Site Management*.xlsx'; $latest=$null; foreach($file in $files){if($null -eq $latest -or $file.LastWriteTime -gt $latest.LastWriteTime){$latest=$file}}; if($latest){$latest.FullName}"`) do set "MASTER_FILE=%%F"
if not defined MASTER_FILE (
    echo [ERROR] Site Management*.xlsx tidak ditemukan di folder ini.
    exit /b 1
)
echo [OK] Master file: %MASTER_FILE%

:: Build NOC Tools (Unified App: Massive Checker + CCTV Report)
echo.
echo Memulai kompilasi PyInstaller...
%PYTHON_EXE% -m PyInstaller --noconfirm --clean ^
    --distpath dist --workpath "build\NOC Tools" "NOC Tools.spec"
if errorlevel 1 (
    echo [ERROR] Build NOC Tools gagal.
    exit /b 1
)
echo [OK] NOC Tools berhasil dibuild.

:: Build one WebView executable for both web workspaces
%PYTHON_EXE% -m PyInstaller --noconfirm --clean ^
    --distpath "dist\bin" --workpath "build\NOC Web Tools" "NOC Web Tools.spec"
if errorlevel 1 (
    echo [ERROR] Build NOC Web Tools gagal.
    exit /b 1
)
echo [OK] NOC Web Tools berhasil dibuild.

:: Build Capture Modem as a standalone PyQt/Playwright application
%PYTHON_EXE% -m PyInstaller --noconfirm --clean ^
    --distpath "dist\bin" --workpath "build\Capture Modem" "Capture_Modem.spec"
if errorlevel 1 (
    echo [ERROR] Build Capture Modem gagal.
    exit /b 1
)
echo [OK] Capture Modem berhasil dibuild.

:: Remove retired executables so old copies cannot leak into a laptop package
if exist "dist\bin\NOC VPN Manager.exe" del /f /q "dist\bin\NOC VPN Manager.exe"
if exist "dist\bin\NOC Web Dashboard.exe" del /f /q "dist\bin\NOC Web Dashboard.exe"
if exist "dist\bin\NOC Web Ticket Checker.exe" del /f /q "dist\bin\NOC Web Ticket Checker.exe"
if exist "dist\NOC VPN Manager.exe" del /f /q "dist\NOC VPN Manager.exe"
if exist "dist\NOC Web Dashboard.exe" del /f /q "dist\NOC Web Dashboard.exe"
if exist "dist\NOC Web Ticket Checker.exe" del /f /q "dist\NOC Web Ticket Checker.exe"

:: Create a deterministic portable package without local credentials or build caches
%PYTHON_EXE% package_portable.py --output "installer_output\NOC_Tools_Portable.zip"
if errorlevel 1 (
    echo [ERROR] Gagal membuat paket portable.
    exit /b 1
)
echo [OK] Paket portable dibuat di installer_output\NOC_Tools_Portable.zip.

echo.
echo ============================================================
echo  BUILD SUKSES!
echo  Portable package siap dikirim:
echo   - installer_output\NOC_Tools_Portable.zip
echo ============================================================

echo.
