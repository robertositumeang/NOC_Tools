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
- Build the administrator desktop app with `.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean "NOC Tools Administrator.spec"`. The result is `dist\NOC Tools Administrator.exe`. It signs in to the Cloudflare Worker and provides first-admin setup, operator creation, password reset, account activation/deactivation, license issuance, and issuance history.
- For first-time administrator setup, deploy the Worker and D1 schema below, then set the Worker secret `ADMIN_BOOTSTRAP_SECRET` in Cloudflare. Open the administrator app, enter the HTTPS Worker URL, and use **Setup administrator pertama** with a new administrator username, display name, and password. This secret is only for initial setup and must not be packaged in the executable or shared in chat. After creating the first administrator, subsequent access uses its username and password.
- New license keys use the signed `NOC-LIC3-` format and are bound to one email address and one Machine ID. The operator enters both the email and key in the activation dialog. Existing `NOC-LIC2-` licenses remain valid until they expire but cannot be redeemed through the new activation service.
- A key can activate one email/device pair only. The Cloudflare Worker verifies each signed key and records activation in the `license_activations` table in D1. Repeating the exact same request returns the original activation proof so a lost network response can be retried; a different key for an already activated email is rejected.
- The license duration starts when the Worker first accepts the key, not when the administrator issues it. The Worker returns a signed activation proof that is stored by the app and checked locally, so normal use remains offline after activation. The D1 activation database and its backups are essential: losing them removes the central record that prevents reuse.
- Deploy `cloudflare/worker.mjs` to the `noc-license-api` Worker, apply `cloudflare/schema.sql` to the `noc-license-db` D1 database, bind D1 as `DB`, and configure both `LICENSE_SIGNING_PRIVATE_KEY` and the one-time `ADMIN_BOOTSTRAP_SECRET` Worker secrets. See [LICENSE_ACTIVATION_WORKFLOW.md](LICENSE_ACTIVATION_WORKFLOW.md) for the Cloudflare deployment and verification steps.
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

## NOC VPN Manager

The separate PyQt6 application in `VPN\` provides a compact Windows interface
for existing WireGuard for Windows tunnel services and the official FortiClient
VPN client. It does not replace either VPN client or assert tunnel connectivity.
Use Python 3.11 or newer on Windows 10/11.

### Setup and launch (Windows PowerShell)

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m VPN.main
```

The existing `PyQt6` requirement is shared with NOC Tools. The VPN manager has
no additional runtime dependencies.

### Windows integration and privileges

- WireGuard profiles must already be imported into the official WireGuard for
  Windows application. The manager discovers registered
  `WireGuardTunnel$<TunnelName>` services and uses Windows `sc.exe` to query,
  start, or stop those services. Starting or stopping a service may require
  running the manager with appropriate Windows privileges; it never elevates
  itself or edits tunnel configurations.
- FortiClient is detected in common `Program Files` locations and launched
  directly. Sign-in, MFA, certificate validation, enterprise policy, and
  connection must be completed inside the official FortiClient application.
  Direct FortiClient connect/disconnect is intentionally not implemented
  because no supported client interface is assumed.
- A running WireGuard service or FortiClient process does not prove that a VPN
  tunnel is connected or reachable. The readiness indicator reports only
  installed-client and Windows-service availability.
- No credentials are collected or stored, and the activity log does not record
  credentials.

### Tests, packaging, and troubleshooting

Run the controller and UI tests from the repository root:

```powershell
python -m pip install pytest
python -m pytest VPN\tests
```

Build a standalone Windows executable from the repository root:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean "VPN\NOC VPN Manager.spec"
```

If no WireGuard profiles appear, import the tunnel in WireGuard for Windows
first, then use **Refresh**. If a service operation reports access denied, close
the manager, relaunch it with the required Windows privileges, and retry.
FortiClient detection checks common install paths; if the client is installed
elsewhere, add that path to the controller's `candidate_paths` when integrating
the deployment-specific location. If Windows blocks service control or process
detection, review local policy and permissions rather than bypassing them.

---

## Building Standalone Portable EXE ("Tinggal Pakai")

To compile the application into a single standalone `.exe` that can be copied to any Windows PC/laptop and run directly **without installing Python or any libraries**:

```powershell
python -m pip install pyinstaller
.\build_exe.bat
```

The resulting binary will be created at `dist\NOC Dashboard.exe`.
You can copy this `.exe` file to a USB flash drive or share it via cloud storage, and any user can immediately run it by double-clicking.