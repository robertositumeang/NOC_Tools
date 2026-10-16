@echo off
setlocal
title Uninstall NOC Tools

echo.
echo ============================================================
echo  UNINSTALL NOC TOOLS
echo ============================================================
echo.
echo This will remove the installed or portable NOC Tools app,
echo its local license, Ticket Checker cache/settings, and display
echo preferences for the current Windows user.
echo.
echo Exported reports and other files outside the app folder will
echo be kept. Run this file as the same Windows user as NOC Tools.
echo.
choice /C YN /N /M "Continue with uninstall? [Y/N] "
if errorlevel 2 exit /b 0

set "NOC_UNINSTALL_PORTABLE_ROOT="
if exist "%~dp0NOC Tools.exe" set "NOC_UNINSTALL_PORTABLE_ROOT=%~dp0"

echo.
echo Waiting for NOC Tools windows to close...
:WAIT_FOR_APPS
set "NOC_APP_RUNNING="
for %%N in ("NOC Tools.exe" "NOC Web Tools.exe" "Capture_Modem.exe" "NOC Tools Administrator.exe") do (
    tasklist /FI "IMAGENAME eq %%~N" /NH 2>nul | find /I "%%~N" >nul && set "NOC_APP_RUNNING=1"
)
if defined NOC_APP_RUNNING (
    echo Close all NOC Tools windows. This file will continue automatically.
    timeout /T 3 /NOBREAK >nul
    goto WAIT_FOR_APPS
)

echo Removing the application and its local data...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $registryPaths=@('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall','HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'); $uninstallers=@{}; $registered=$false; foreach($registryPath in $registryPaths){if(Test-Path -LiteralPath $registryPath){foreach($key in Get-ChildItem -LiteralPath $registryPath){$entry=Get-ItemProperty -LiteralPath $key.PSPath; if($entry.DisplayName -eq 'NOC Tools'){$registered=$true; $uninstaller=$null; $installLocation=[string]$entry.InstallLocation; if($installLocation){$candidate=Join-Path $installLocation 'unins000.exe'; if(Test-Path -LiteralPath $candidate){$uninstaller=$candidate}}; if((-not $uninstaller) -and ([string]$entry.UninstallString -match '^""?([^""]+?\.exe)""?(?:\s|$)')){$candidate=$Matches[1]; if(Test-Path -LiteralPath $candidate){$uninstaller=$candidate}}; if($uninstaller){$uninstallers[$uninstaller]=$true}}}}}; foreach($installLocation in @((Join-Path $env:ProgramFiles 'NOC Tools'),($env:ProgramFiles + ' (x86)\NOC Tools'),($env:LOCALAPPDATA + '\Programs\NOC Tools'))){$candidate=Join-Path $installLocation 'unins000.exe'; if(Test-Path -LiteralPath $candidate){$uninstallers[$candidate]=$true}}; if($registered -and $uninstallers.Count -eq 0){throw 'NOC Tools is registered, but its uninstaller could not be found.'}; foreach($uninstaller in $uninstallers.Keys){$result=Start-Process -FilePath $uninstaller -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART' -Wait -PassThru; if($result.ExitCode -ne 0){throw ('NOC Tools uninstaller failed with exit code ' + $result.ExitCode)}}; $portableRoot=$env:NOC_UNINSTALL_PORTABLE_ROOT; if($portableRoot){foreach($relativePath in @('NOC Tools.exe','app_icon.ico','README_PORTABLE.txt','bin\NOC Web Tools.exe','bin\Capture_Modem.exe')){$target=Join-Path $portableRoot $relativePath; if(Test-Path -LiteralPath $target -PathType Leaf){Remove-Item -LiteralPath $target -Force}}; $bin=Join-Path $portableRoot 'bin'; if((Test-Path -LiteralPath $bin -PathType Container) -and -not (Get-ChildItem -LiteralPath $bin -Force)){Remove-Item -LiteralPath $bin -Force}}; $licenseData=Join-Path $env:APPDATA 'NOC_Tools'; if(Test-Path -LiteralPath $licenseData -PathType Container){Remove-Item -LiteralPath $licenseData -Recurse -Force}; $ticketData=Join-Path $env:USERPROFILE '.noc_cache\ticket_checker'; if(Test-Path -LiteralPath $ticketData -PathType Container){Remove-Item -LiteralPath $ticketData -Recurse -Force}; $cacheRoot=Join-Path $env:USERPROFILE '.noc_cache'; if((Test-Path -LiteralPath $cacheRoot -PathType Container) -and -not (Get-ChildItem -LiteralPath $cacheRoot -Force)){Remove-Item -LiteralPath $cacheRoot -Force}; $displaySettings='HKCU:\Software\PT. KEREAKTIF INDONESIA\NOC Tools'; if(Test-Path -LiteralPath $displaySettings){Remove-Item -LiteralPath $displaySettings -Recurse -Force}; Write-Output 'NOC Tools and its local license, cache, and display settings have been removed.'"
if errorlevel 1 (
    echo.
    echo Uninstall did not complete. Review the PowerShell error above.
    pause
    exit /b 1
)

echo.
echo Uninstall completed. Exported reports were not removed.
pause
exit /b 0
