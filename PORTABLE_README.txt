NOC TOOLS - PORTABLE WINDOWS PACKAGE

1. Extract the entire ZIP to a writable folder on a Windows 10/11 x64 laptop.
2. Keep NOC Tools.exe, bin, and app_icon.ico together. The default Site
   Management database is bundled inside NOC Tools.exe.
3. Start the operator application by opening NOC Tools.exe.
4. Microsoft Edge WebView2 Runtime and an internet connection are required.
   Install or repair the Evergreen WebView2 Runtime if the web workspaces
   cannot open.
5. Login, license activation, and Google Sheets features require internet
   access. The official license service URL is built into the application; no
   PowerShell configuration is required. Activate a license on each
   authorized laptop. Licenses are bound to an email and device; moving files
   does not transfer a device activation. Administrators using a different
   Worker may optionally set NOC_LICENSE_API_URL before starting the app.
6. The administrator executable is deliberately not included in this public
   operator package. Keep it separate and share it only through an approved
   private channel with authorized administrators.

The portable package does not require Python to be installed. Capture Modem
requires network access to the target modem and uses the packaged browser
automation runtime.
