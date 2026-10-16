# NOC Monitor | Massive Site Down Analyzer

A professional desktop application built with **PyQt6** for Network Operations Center (NOC) engineers to ingest, correlate, and normalize **ZTE** and **Fiberhome** alarm logs, cross-reference with **Site Management** master databases, and detect concurrent outage peaks across VSAT providers and spotbeams.

Designed with modern **Qt Style Sheet (QSS) Glassmorphism**, crisp per-monitor High-DPI vector rendering, and zero-dependency standalone portability.

---

## Getting Started

In Windows PowerShell, navigate to the project directory and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

### Authentication and License Administration
- For the complete license issuance, activation, offline verification, deployment, and troubleshooting workflow, see [LICENSE_ACTIVATION_WORKFLOW.md](LICENSE_ACTIVATION_WORKFLOW.md).
- Operator accounts are managed centrally in Cloudflare D1 by **NOC Tools Administrator**. Operator login requires an internet connection; the application sends credentials over HTTPS and the Worker stores password hashes, not plaintext passwords. Do not distribute a `users.json` file.
- Build the administrator desktop app with `.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean "NOC Tools Administrator.spec"`. The result is `dist\NOC Tools Administrator.exe`. It signs in to the Cloudflare Worker and provides first-admin setup, operator creation, password reset, account activation/deactivation, license issuance, issuance history, recovery of unactivated license keys, and selective email/device-binding cleanup. Deleting selected emails removes issued records and current device bindings but retains activation history to prevent old keys from being reused; issue a new key after releasing a device.
- For first-time administrator setup, deploy the Worker and D1 schema below, then set the Worker secret `ADMIN_BOOTSTRAP_SECRET` in Cloudflare. Open the administrator app, enter the HTTPS Worker URL, and use **Setup administrator pertama** with a new administrator username, display name, and password. This secret is only for initial setup and must not be packaged in the executable or shared in chat. After creating the first administrator, subsequent access uses its username and password.
- New license keys use the signed `NOC-LIC3-` format and are bound to one email address and one Machine ID. The operator enters both the email and key in the activation dialog. Existing `NOC-LIC2-` licenses remain valid until they expire but cannot be redeemed through the new activation service.
- A key can activate one email/device pair only. The Cloudflare Worker verifies each signed key and records activation in the `license_activations` table in D1. Repeating the exact same request returns the original activation proof so a lost network response can be retried; a different key for an already activated email is rejected.
- The license duration starts when the Worker first accepts the key, not when the administrator issues it. The Worker returns a signed activation proof that is stored by the app and checked locally, so normal use remains offline after activation. The D1 activation database and its backups are essential: losing them removes the central record that prevents reuse.
- Deploy the Worker with `npx wrangler deploy --config cloudflare/wrangler.toml`; it binds the existing `noc-license-db` D1 database. Apply `cloudflare/schema.sql` when provisioning a new database and ensure the `LICENSE_SIGNING_PRIVATE_KEY` and one-time `ADMIN_BOOTSTRAP_SECRET` Worker secrets are configured. See [LICENSE_ACTIVATION_WORKFLOW.md](LICENSE_ACTIVATION_WORKFLOW.md) for deployment and verification steps.
- On each Windows client, configure the Worker URL once from PowerShell with `setx NOC_LICENSE_API_URL "https://noc-license-api.<account>.workers.dev"` (replace the example with the URL shown in Cloudflare) and open a new terminal before starting the app. Workers.dev provides HTTPS; keep certificate verification enabled.
- The Ed25519 private signing key is held only as the Cloudflare Worker secret and must never be included in the repository or either executable. The app contains only the matching public key in `license_crypto.py`. Do not replace a deployed signing key unless the application is rebuilt with its matching public key and licenses are reissued.
- The activation Worker stores normalized email addresses and activation metadata in Cloudflare D1. Protect the Worker Secret and back up the D1 database. Activation validates that the submitted email matches the signed key; it does not send an email OTP or independently prove mailbox ownership. `license_server.py` remains available as an optional local SQLite service, but its registry is separate from Cloudflare D1.

### Automatic File Discovery
- If alarm export files are located in the application directory, the app identifies vendors directly from column headers (`ZTE` or `Fiberhome`) and automatically selects the most recent file per vendor by modification time.
- Supported file types: `.xlsx`, `.xls` (BIFF8), `.csv` (including files with metadata rows before headers), and `.zip` bundles containing alarm workbooks.
- The built-in Site Management database (`Site Management*.xlsx`) is embedded as the default master (~1,404 sites). You can switch between **Default Master** and **Custom Master File** in the sidebar.
- Fiberhome alarm names containing `S1 Link` are included in the default alarm-name selection alongside the other preferred down alarms.

---

## Features & UI

### 1. Modern PyQt6 Themes (QSS)
Toggle effortlessly between 4 curated themes via the **THEME** picker in the top navigation bar:
- **Obsidian Glass (Dark)**: Deep obsidian space (`#0a0e17`) with frosted glass panels and electric cyan accents.
- **Emerald Cyber (Dark)**: Tactical midnight black (`#090d10`) with glowing emerald green indicators.
- **Neumorphic Slate (Light)**: Crisp clay/neumorphic light aesthetic (`#eef2f6`) with soft dual-tone shadow borders.
- **Midnight OLED (Ultra Dark)**: True jet-black palette (`#030712`) with vibrant sky-blue accents, optimized for video walls.

### 2. High-DPI Resolution & Sharp Typography
- Full native Qt6 High-DPI scaling: fonts, tables, icons, and 1px borders render razor-sharp on any screen (1080p laptops at 125%/150%, 2K, 4K) without any blurring or pixelation.
- Choose an application-only display scale (100%, 125%, 150%, or 175%) and window resolution side by side below the application buttons. The scale is applied to NOC Tools without changing Windows display settings; changing it restarts the selected app once.
- The selected resolution sets the app window size and is automatically limited to the current screen. The default profile is 100% scale at 1920 × 1080; closing either application returns to the launcher immediately, while in-progress background work finishes safely.
- Each selected application opens maximized with the native Windows title bar and minimize, maximize/restore, and close buttons.
- A branded animated loading screen appears while NOC Tools prepares the application after launch.

### 3. Two-Tier Filter & Scope Deck
- **Tier 1 (Filters & Presets)**:
  - `VSAT Providers` multi-select menu.
  - `Alarm Categories` multi-select menu.
  - `Alarm Names` searchable checklist popover.
  - Quick presets: **Today** (midnight to now) and **Last 24h** (previous 24 hours to now).
- **Tier 2 (Time Scope & Execution)**:
  - Date & Time pickers with popup calendars.
  - **`⟳ Apply Filter & Scope`** prominent action button positioned with ample breathing room (never cut off).

### 4. Outage Analysis & Incident Tracking
- **Hero KPI Cards**: Instant visual summary of *Affected Sites in Range*, *Peak Concurrent Down*, and *Massive Outage Incidents*.
- **Configurable Threshold**: Set custom threshold (default: $\ge 5$ simultaneous down sites) for flagging massive outage incidents.
- **Fast QTableWidget Tables**:
  - Click any column header to sort alphabetically, numerically, or chronologically.
  - Rows with Massive Outages highlighted in soft rose/burgundy with bold `YES` badges.
  - Right-click any row in the **VSAT Outage Summary** table and select **Export Selected Rows to Excel...**.

### 5. Multi-Sheet Excel Reports
Generates structured Excel workbooks containing 3 auto-formatted sheets:
1. `Consolidated Alarms`
2. `VSAT Summary`
3. `Sites at Peak`

## Windows Laptop Distribution

The supported laptop distribution is a portable ZIP. It bundles the operator
launcher, combined Dashboard/Ticket Checker, Capture Modem, and the Site
Management workbook. If the private administrator executable is available at
build time, it is included separately under `Admin`. The package never includes
VPN Manager or a local `users.json` credential file.

### Requirements on the target laptop

- Windows 10 or Windows 11, 64-bit.
- Microsoft Edge WebView2 Evergreen Runtime for Dashboard and Ticket Checker.
- Internet access for operator sign-in, license activation, and Google Sheets
  features. Modem capture also needs access to the target modem.
- Configure `NOC_LICENSE_API_URL` as described in the authentication section
  above. License activation is tied to an email and device. Each laptop must be
  authorized for its own activation; copying the ZIP does not bypass licensing.
- NOC Tools Administrator is for authorized administrators only. Its separate
  executable requires administrator credentials and is not exposed in the
  operator launcher.

Extract the entire ZIP to a writable folder and run `NOC Tools.exe`. Keep the
`bin`, `data`, `Admin`, and icon files beside the launcher; do not run it from
inside the ZIP. Python does not need to be installed on a target laptop.

### Build and create the portable ZIP

Run on a Windows build machine with the project dependencies and PyInstaller:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r Capture_Modem\requirements.txt pyinstaller
.\build_exe.bat
```

The build produces the current executables in `dist` and creates
`installer_output\NOC_Tools_Portable.zip`. The archive contains only explicitly
listed runtime files and the portable instructions; it excludes local account
data, caches, virtual environments, build trees, retired standalone web tools,
and VPN Manager. NOC Tools Administrator remains a separate, privately
controlled utility; when available, the portable archive stores it under
`Admin` without adding it to the operator launcher.
The Capture Modem sitelist and Paket 10/11 CCTV templates are bundled in their
workspaces and can also be downloaded from the UI.

`installer.iss` provides an Inno Setup alternative with an optional shortcut
for the administrator utility. Build it with Inno Setup 6 after running
`build_exe.bat`. The admin PyInstaller spec uses paths relative to the project,
so rebuilding does not depend on this workspace's current drive or folder.