"""Auto-Update Module for NOC Tools.

Handles checking for updates via GitHub Releases API, parsing semantic versions,
downloading updates in a background worker, and applying self-updates on Windows.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QSettings, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

import requests

from noc_brand import APP_NAME, APP_VERSION

DEFAULT_GITHUB_REPO = "robertositumeang/NOC_Tools"
GITHUB_API_TIMEOUT = 8


# ── Configuration & Repo Helpers ──────────────────────────────────────────────
def get_update_settings() -> QSettings:
    return QSettings("PT. KEREAKTIF INDONESIA", "NOC Tools")


def get_github_repo() -> str:
    settings = get_update_settings()
    repo = str(settings.value("update/githubRepo", DEFAULT_GITHUB_REPO)).strip()
    return repo or DEFAULT_GITHUB_REPO


def set_github_repo(repo: str) -> None:
    settings = get_update_settings()
    settings.setValue("update/githubRepo", repo.strip())


def configure_github_repo_dialog(parent: QWidget | None = None) -> str | None:
    """Prompt user to set or change the GitHub repository."""
    current = get_github_repo()
    repo, ok = QInputDialog.getText(
        parent,
        "Pengaturan Repository Update",
        "Masukkan path GitHub repository (format: pemilik/nama-repo):\n"
        "Contoh: PT-Lindu-Putra-Utama/NOC-Project",
        text=current,
    )
    if ok and repo.strip():
        set_github_repo(repo.strip())
        return repo.strip()
    return None


# ── Version Parsing ───────────────────────────────────────────────────────────
def parse_version(version_str: str) -> tuple[int, ...]:
    """Extract numeric components from version strings like 'v1.2.3', '1.0.0', 'v2.0-beta'.

    Returns a tuple of integers for reliable semantic comparison.
    """
    clean = re.sub(r"^[vV]", "", version_str.strip())
    # Find all contiguous digit sequences
    parts = re.findall(r"\d+", clean)
    if not parts:
        return (0,)
    return tuple(int(p) for p in parts)


def is_newer_version(current: str, candidate: str) -> bool:
    """Returns True if candidate version is strictly newer than current version."""
    v_curr = parse_version(current)
    v_cand = parse_version(candidate)

    # Pad with zeros to make lengths equal
    max_len = max(len(v_curr), len(v_cand))
    v_curr_padded = v_curr + (0,) * (max_len - len(v_curr))
    v_cand_padded = v_cand + (0,) * (max_len - len(v_cand))

    return v_cand_padded > v_curr_padded


# ── GitHub Releases API ───────────────────────────────────────────────────────
def check_github_release(repo: str | None = None) -> dict[str, Any] | None:
    """Queries GitHub Releases API for the latest published release.

    Returns a dictionary of release details, or None if no valid release is found.
    Raises requests.exceptions.RequestException on network failure.
    """
    target_repo = repo or get_github_repo()
    url = f"https://api.github.com/repos/{target_repo}/releases/latest"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": f"NOCTools-Updater/{APP_VERSION}",
    }

    response = requests.get(url, headers=headers, timeout=GITHUB_API_TIMEOUT)
    if response.status_code == 404:
        # No release found or repository is private/non-existent
        return None
    response.raise_for_status()

    data = response.json()
    tag_name = data.get("tag_name", "")
    release_name = data.get("name") or tag_name
    body = data.get("body") or "Tidak ada catatan rilis."
    html_url = data.get("html_url") or f"https://github.com/{target_repo}/releases"
    published_at = data.get("published_at", "")

    # ── Modular / Delta Asset Detection ──
    assets = data.get("assets", [])
    download_url = None
    asset_name = None
    asset_size = 0

    base_app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent

    # Known module locations relative to app root
    KNOWN_MODULE_PATHS = {
        "NOC Tools.exe": Path("NOC Tools.exe"),
        "Capture_Modem.exe": Path("bin/Capture_Modem.exe"),
        "NOC Web Dashboard.exe": Path("bin/NOC Web Dashboard.exe"),
        "NOC Web Ticket Checker.exe": Path("bin/NOC Web Ticket Checker.exe"),
        "NOC VPN Manager.exe": Path("bin/NOC VPN Manager.exe"),
        "Site Management.xlsx": Path("data/Site Management.xlsx"),
    }

    modular_items: list[dict[str, Any]] = []

    for a in assets:
        a_name = a.get("name", "")
        a_url = a.get("browser_download_url")
        a_size = a.get("size", 0)

        # Main launcher fallback
        if a_name.lower().endswith(".exe") and "noc" in a_name.lower() and not download_url:
            download_url = a_url
            asset_name = a_name
            asset_size = a_size

        # Check if asset matches any known or new modular component
        for known_name, rel_path in KNOWN_MODULE_PATHS.items():
            if a_name.lower() == known_name.lower():
                local_file = base_app_dir / rel_path
                is_missing = not local_file.exists()
                size_diff = is_missing or abs(local_file.stat().st_size - a_size) > 1024  # different size
                
                modular_items.append({
                    "name": known_name,
                    "target_rel_path": str(rel_path),
                    "download_url": a_url,
                    "size": a_size,
                    "is_missing": is_missing,
                    "needs_update": size_diff,
                })
                break
        else:
            # New feature or addon executable in bin/
            if a_name.endswith(".exe") and a_name not in ("NOC Tools.exe", "NOC_Tools.exe", "NOC_Tools_Setup.exe"):
                rel_path = Path("bin") / a_name
                local_file = base_app_dir / rel_path
                modular_items.append({
                    "name": a_name,
                    "target_rel_path": str(rel_path),
                    "download_url": a_url,
                    "size": a_size,
                    "is_missing": not local_file.exists(),
                    "needs_update": True,
                })

    # Overall update flag: version tag is newer OR any modular component is missing/needs update
    pending_modular = [m for m in modular_items if m.get("needs_update")]
    has_update = is_newer_version(APP_VERSION, tag_name) or bool(pending_modular)

    return {
        "repo": target_repo,
        "tag_name": tag_name,
        "name": release_name,
        "body": body,
        "html_url": html_url,
        "published_at": published_at,
        "download_url": download_url,
        "asset_name": asset_name,
        "asset_size": asset_size,
        "has_update": has_update,
        "modular_items": modular_items,
        "pending_modular": pending_modular,
    }


# ── Background Worker Threads ─────────────────────────────────────────────────
class CheckUpdateWorker(QThread):
    """Threaded worker to check GitHub release without blocking the UI."""
    update_found = pyqtSignal(dict)      # Emitted when a newer version exists
    up_to_date = pyqtSignal(dict)        # Emitted when already on the latest version
    no_release = pyqtSignal(str)         # Emitted when repo has no releases
    check_failed = pyqtSignal(str)       # Emitted on network / API error

    def __init__(self, repo: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repo = repo

    def run(self) -> None:
        try:
            info = check_github_release(self.repo)
            if info is None:
                self.no_release.emit(self.repo or get_github_repo())
            elif info.get("has_update"):
                self.update_found.emit(info)
            else:
                self.up_to_date.emit(info)
        except requests.exceptions.RequestException as err:
            self.check_failed.emit(str(err))
        except Exception as err:
            self.check_failed.emit(f"Error: {err}")


class ModularDownloadWorker(QThread):
    """Threaded worker to download multiple modular files (deltas/new features)."""
    item_progress = pyqtSignal(str, int, int, float)  # (item_name, done, total, pct)
    overall_progress = pyqtSignal(int, int)           # (current_index, total_items)
    all_finished = pyqtSignal(list)                   # list of successfully updated relative paths
    failed = pyqtSignal(str)                          # error message

    def __init__(self, items: list[dict[str, Any]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.items = items
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        base_app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        updated_paths: list[str] = []
        total_items = len(self.items)

        try:
            for idx, item in enumerate(self.items, 1):
                if self._cancelled:
                    return

                name = item.get("name", "modul")
                url = item.get("download_url")
                rel_path = item.get("target_rel_path")
                if not url or not rel_path:
                    continue

                self.overall_progress.emit(idx, total_items)

                # Destination file path
                dest_path = base_app_dir / rel_path
                temp_dest = dest_path.with_suffix(dest_path.suffix + ".part")
                temp_dest.parent.mkdir(parents=True, exist_ok=True)

                headers = {"User-Agent": f"NOCTools-Updater/{APP_VERSION}"}
                with requests.get(url, headers=headers, stream=True, timeout=20) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get("content-length", 0))
                    downloaded = 0

                    with open(temp_dest, "wb") as f:
                        for chunk in r.iter_content(chunk_size=65536):
                            if self._cancelled:
                                f.close()
                                temp_dest.unlink(missing_ok=True)
                                return
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                pct = (downloaded / total_size * 100) if total_size > 0 else 0.0
                                self.item_progress.emit(name, downloaded, total_size, pct)

                # Move downloaded temp file into place (safely swap old if locked)
                if dest_path.exists():
                    old_backup = dest_path.with_suffix(dest_path.suffix + ".old")
                    try:
                        dest_path.replace(old_backup)
                    except Exception:
                        pass
                
                temp_dest.replace(dest_path)
                updated_paths.append(rel_path)

            self.all_finished.emit(updated_paths)
        except Exception as err:
            self.failed.emit(str(err))


# ── Self-Update Installer (Windows) ───────────────────────────────────────────
def apply_update_and_restart(new_exe_path: str | Path) -> None:
    """Replaces current running .exe with new_exe_path using a detached batch script and restarts."""
    new_path = Path(new_exe_path).resolve()
    current_exe = Path(sys.executable).resolve()

    if not getattr(sys, "frozen", False):
        # Development mode (running from Python script)
        QMessageBox.information(
            None,
            "Mode Development",
            f"Update berhasil didownload ke:\n{new_path}\n\n"
            "Karena Anda menjalankan dari source code (.py), file executable tidak ditimpa otomatis. "
            "Silakan gunakan file .exe tersebut atau lakukan git pull.",
        )
        return

    # Create helper batch updater script in temp directory
    batch_content = f"""@echo off
setlocal
echo ======================================================
echo  Menerapkan Update {APP_NAME}...
echo ======================================================

:: Beri jeda 2 detik agar proses lama benar-benar tertutup
timeout /t 2 /nobreak >nul

:: Timpa file executable lama dengan file baru
move /y "{new_path}" "{current_exe}" >nul
if errorlevel 1 (
    copy /y "{new_path}" "{current_exe}" >nul
    del /f /q "{new_path}" >nul 2>&1
)

:: Jalankan kembali aplikasi yang sudah diperbarui
start "" "{current_exe}"

:: Bersihkan file script batch ini sendiri
del "%~f0" >nul 2>&1
"""

    temp_batch = Path(tempfile.gettempdir()) / "noc_tools_updater.bat"
    temp_batch.write_text(batch_content, encoding="utf-8")

    # Spawn the batch updater as a detached background process
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    subprocess.Popen(
        ["cmd.exe", "/c", str(temp_batch)],
        creationflags=creationflags,
        close_fds=True,
    )

    # Clean exit of current application
    app = QApplication.instance()
    if app is not None:
        app.quit()
    sys.exit(0)


# ── Update Dialog UI ──────────────────────────────────────────────────────────
class UpdateDialog(QDialog):
    """Interactive Dialog displaying update information, changelog, and download progress."""

    def __init__(self, release_info: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.release_info = release_info
        self.download_worker: DownloadUpdateWorker | None = None

        self.setWindowTitle(f"Software Updates — {APP_NAME}")
        self.setMinimumSize(560, 420)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header card
        header = QHBoxLayout()
        icon_lbl = QLabel("🚀")
        icon_lbl.setStyleSheet("font-size: 32px;")
        header.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_lbl = QLabel("New Version Available!")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: palette(text);")
        title_col.addWidget(title_lbl)

        tag = self.release_info.get("tag_name", "")
        rel_name = self.release_info.get("name", "")
        sub_text = f"Current Version: <b>v{APP_VERSION}</b>  ➔  Latest Version: <b>{tag}</b>"
        sub_lbl = QLabel(sub_text)
        sub_lbl.setStyleSheet("font-size: 13px; color: #38BDF8;")
        title_col.addWidget(sub_lbl)
        header.addLayout(title_col)
        header.addStretch()

        layout.addLayout(header)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: palette(mid); max-height: 1px;")
        layout.addWidget(line)

        # Changelog / Release Notes & Modular Details
        lbl_notes = QLabel("Changelog & Detected Components:")
        lbl_notes.setStyleSheet("font-weight: 600; font-size: 12px;")
        layout.addWidget(lbl_notes)

        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(False)
        raw_body = self.release_info.get("body", "No release notes provided.")
        # Strip raw markdown file links or github references from changelog
        clean_body = re.sub(r"\[([^\]]+)\]\(https?://[^\)]+\)", r"\1", raw_body)
        formatted_body = clean_body.replace("\n", "<br>")

        pending_modular = self.release_info.get("pending_modular", [])
        if pending_modular:
            mod_lines = ["<br><b>📦 Modular Updates & New Features:</b><ul>"]
            for m in pending_modular:
                status_text = "✨ New Feature / Module" if m.get("is_missing") else "🔄 Version Update"
                size_mb = m.get("size", 0) / (1024 * 1024)
                mod_lines.append(f"<li><b>{m.get('name')}</b> ({size_mb:.1f} MB) — <i>{status_text}</i></li>")
            mod_lines.append("</ul><small style='color: #10B981;'>Only the above components will be downloaded efficiently!</small>")
            formatted_body += "".join(mod_lines)

        self.text_browser.setHtml(
            f"<div style='font-family: Segoe UI, sans-serif; font-size: 12px; line-height: 1.4;'>"
            f"<b>{rel_name}</b><br><br>{formatted_body}</div>"
        )
        self.text_browser.setStyleSheet(
            "QTextBrowser { border: 1px solid palette(mid); border-radius: 8px; padding: 8px; }"
        )
        layout.addWidget(self.text_browser, 1)

        # Progress bar (hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("font-size: 11px; color: palette(text);")
        self.status_lbl.setVisible(False)
        layout.addWidget(self.status_lbl)

        # Action Buttons (Clean enterprise style, no GitHub references)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Later")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        has_any_update = self.release_info.get("has_update")
        if has_any_update:
            self.btn_update = QPushButton("⚡ Update Now")
            self.btn_update.setStyleSheet(
                "QPushButton { background-color: #0284C7; color: white; font-weight: bold; padding: 6px 18px; border-radius: 6px; }"
                "QPushButton:hover { background-color: #0369A1; }"
            )
            self.btn_update.clicked.connect(self._start_download)
            btn_layout.addWidget(self.btn_update)
        else:
            self.btn_update = None

        layout.addLayout(btn_layout)

    def _start_download(self) -> None:
        pending_modular = self.release_info.get("pending_modular", [])

        self.progress_bar.setVisible(True)
        self.status_lbl.setVisible(True)
        self.status_lbl.setText("Connecting to update server...")
        if self.btn_update:
            self.btn_update.setEnabled(False)
        self.btn_cancel.setText("Cancel")

        if pending_modular:
            # Download only the specific modular components that changed / new features
            self.download_worker = ModularDownloadWorker(pending_modular, self)
            self.download_worker.item_progress.connect(self._on_modular_item_progress)
            self.download_worker.all_finished.connect(self._on_modular_download_complete)
            self.download_worker.failed.connect(self._on_download_error)
            self.download_worker.start()
        else:
            # Fallback: standard main executable update
            download_url = self.release_info.get("download_url")
            if not download_url:
                QMessageBox.warning(self, "Download Failed", "No update file found on the server.")
                return

            asset_name = self.release_info.get("asset_name") or f"{APP_NAME}_Update.exe"
            target_path = Path(tempfile.gettempdir()) / asset_name

            self.download_worker = ModularDownloadWorker([{
                "name": asset_name,
                "download_url": download_url,
                "target_rel_path": asset_name
            }], self)
            self.download_worker.item_progress.connect(self._on_modular_item_progress)
            self.download_worker.all_finished.connect(lambda paths: self._on_download_complete(str(target_path)))
            self.download_worker.failed.connect(self._on_download_error)
            self.download_worker.start()

    def _on_modular_item_progress(self, name: str, downloaded: int, total: int, pct: float) -> None:
        self.progress_bar.setValue(int(pct))
        d_mb = downloaded / (1024 * 1024)
        t_mb = total / (1024 * 1024)
        if total > 0:
            self.status_lbl.setText(f"Downloading {name}: {d_mb:.1f} MB / {t_mb:.1f} MB ({pct:.0f}%)")
        else:
            self.status_lbl.setText(f"Downloading {name}: {d_mb:.1f} MB...")

    def _on_modular_download_complete(self, updated_paths: list) -> None:
        self.status_lbl.setText("✅ All components updated successfully!")
        self.progress_bar.setValue(100)
        
        updated_list = "\n".join([f"• {p}" for p in updated_paths])
        QMessageBox.information(
            self,
            "Update Complete",
            f"The following modules/features were successfully updated:\n\n{updated_list}\n\n"
            "You can use them immediately without restarting the application."
        )
        self.accept()

    def _on_download_complete(self, target_path: str) -> None:
        self.status_lbl.setText("✅ Download complete! Preparing update...")
        self.progress_bar.setValue(100)

        # Confirm and restart for main executable
        msg = QMessageBox(self)
        msg.setWindowTitle("Update Ready to Install")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("Main application update has been downloaded.")
        msg.setInformativeText(
            "The application will restart automatically to apply the latest version.\n\n"
            "Restart and update now?"
        )
        btn_now = msg.addButton("Restart & Update Now", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_now)
        msg.exec()

        if msg.clickedButton() == btn_now:
            apply_update_and_restart(target_path)
        else:
            self.accept()

    def _on_download_error(self, err_msg: str) -> None:
        self.status_lbl.setText(f"❌ Failed: {err_msg}")
        QMessageBox.critical(self, "Update Download Failed", f"An error occurred while downloading:\n\n{err_msg}")
        if self.btn_update:
            self.btn_update.setEnabled(True)
        self.btn_cancel.setText("Close")

    def reject(self) -> None:
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.cancel()
            self.download_worker.wait(1000)
        super().reject()
