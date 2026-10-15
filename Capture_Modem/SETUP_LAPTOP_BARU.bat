@echo off
title Setup Capture Modem di Laptop Baru
color 0A
echo =====================================================================
echo    SETUP & VERIFIKASI APLIKASI CAPTURE MODEM UNTUK LAPTOP BARU
echo =====================================================================
echo.
cd /d "%~dp0"
echo [1/3] Memeriksa Python di sistem...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [PERINGATAN] Python belum terdeteksi di laptop ini!
    echo Silakan install Python 3.10+ dari python.org atau Microsoft Store.
    echo Centang opsi "Add Python to PATH" saat menginstall.
    pause
    exit /b 1
)
echo Python terdeteksi!
echo.
echo [2/3] Memasang dependensi (PyQt6, Playwright, Pandas, dll)...
pip install -r requirements.txt
echo.
echo [3/3] Menyiapkan Playwright browser engine...
python -m playwright install msedge
echo.
echo =====================================================================
echo    Setup Selesai! Menjalankan aplikasi...
echo =====================================================================
start Capture_Modem.exe
timeout /t 3
