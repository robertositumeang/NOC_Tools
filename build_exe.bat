@echo off
setlocal EnableDelayedExpansion

echo.
echo  ============================================================
echo   NOC Tools - Build Executable
echo   PT. Lindu Putra Utama
echo  ============================================================
echo.

:: Cari file Site Management
set "MASTER_FILE="
for %%F in ("Site Management*.xlsx") do if not defined MASTER_FILE set "MASTER_FILE=%%~fF"
if not defined MASTER_FILE (
    echo [ERROR] Site Management*.xlsx tidak ditemukan di folder ini.
    exit /b 1
)
echo [OK] Master file: %MASTER_FILE%

:: Tutup proses yang mungkin sedang berjalan
taskkill /f /im "NOC Tools.exe"           >nul 2>&1
taskkill /f /im "NOC Tools Hub.exe"       >nul 2>&1
taskkill /f /im "NOC Massive Checker.exe" >nul 2>&1
taskkill /f /im "NOC Dashboard.exe"       >nul 2>&1
taskkill /f /im "MassiveSiteDown.exe"     >nul 2>&1
taskkill /f /im "Extract CCTV ScreenShot v.1.0.0.exe" >nul 2>&1

:: Build NOC Tools (Unified App: Massive Checker + CCTV Report)
echo.
echo Memulai kompilasi PyInstaller...
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name "NOC Tools" ^
    --icon "%CD%\app_icon.ico" ^
    --distpath dist --workpath build ^
    --hidden-import "pythoncom" ^
    --hidden-import "pywintypes" ^
    --hidden-import "win32com.client" ^
    --hidden-import "updater" ^
    --hidden-import "auth" ^
    --hidden-import "PIL.ImageStat" ^
    --collect-submodules "PIL" ^
    --add-data "%MASTER_FILE%;site_management" ^
    --add-data "%CD%\CCTV_Report;CCTV_Report" ^
    --add-data "%CD%\app_icon.ico;." ^
    app.py
if errorlevel 1 (
    echo [ERROR] Build NOC Tools gagal.
    exit /b 1
)
echo [OK] NOC Tools berhasil dibuild.

:: Update Desktop jika ada
if exist "%USERPROFILE%\OneDrive\Desktop" (
    copy /y "dist\NOC Tools.exe" "%USERPROFILE%\OneDrive\Desktop\NOC Tools.exe" >nul 2>&1
    echo [OK] Shortcut di OneDrive Desktop diperbarui.
)
if exist "%USERPROFILE%\Desktop" (
    copy /y "dist\NOC Tools.exe" "%USERPROFILE%\Desktop\NOC Tools.exe" >nul 2>&1
    echo [OK] Shortcut di Desktop diperbarui.
)

echo.
echo ============================================================
echo  BUILD SUKSES!
echo  Executable siap pakai di folder dist\:
echo   - dist\NOC Tools.exe (Unified Single Executable)
echo ============================================================

echo.
