@echo off
setlocal
title NOC Tools - Perbaikan URL Aktivasi

echo Mengatur URL layanan aktivasi yang benar...
set "NOC_LICENSE_API_URL=https://noc-license-api.pasitumeangroberto.workers.dev"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[Environment]::SetEnvironmentVariable('NOC_LICENSE_API_URL', 'https://noc-license-api.pasitumeangroberto.workers.dev', 'User')"
if errorlevel 1 (
    echo Gagal menyimpan URL layanan untuk akun Windows ini.
    echo Coba jalankan file ini kembali, atau hubungi administrator.
    pause
    exit /b 1
)

if not exist "%~dp0NOC Tools.exe" (
    echo NOC Tools.exe tidak ditemukan.
    echo Letakkan file BAT ini di folder yang sama dengan NOC Tools.exe.
    pause
    exit /b 1
)

echo.
echo Pastikan semua jendela NOC Tools yang sedang terbuka sudah ditutup.
:WAIT_FOR_APP
tasklist /FI "IMAGENAME eq NOC Tools.exe" /NH | find /I "NOC Tools.exe" >nul
if not errorlevel 1 (
    echo Menunggu NOC Tools ditutup...
    timeout /t 2 /nobreak >nul
    goto WAIT_FOR_APP
)

echo Menjalankan NOC Tools dengan URL layanan yang benar...
pushd "%~dp0"
start "" "NOC Tools.exe"
popd
exit /b 0
