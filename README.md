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

---

## Building Standalone Portable EXE ("Tinggal Pakai")

To compile the application into a single standalone `.exe` that can be copied to any Windows PC/laptop and run directly **without installing Python or any libraries**:

```powershell
python -m pip install pyinstaller
.\build_exe.bat
```

The resulting binary will be created at `dist\NOC Dashboard.exe`.
You can copy this `.exe` file to a USB flash drive or share it via cloud storage, and any user can immediately run it by double-clicking.