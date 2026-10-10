"""Auto-Update Module for NOC Tools.

Handles checking for updates via GitHub Releases API, parsing semantic versions,
downloading updates in a background worker, and applying self-updates on Windows.
"""
from __future__ import annotations

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

    # Look for executable asset (.exe)
    assets = data.get("assets", [])
    download_url = None
    asset_name = None
    asset_size = 0

    # Prefer assets named "NOC Tools.exe", "NOC_Tools.exe", or any .exe
    for a in assets:
        name = a.get("name", "")
        if name.lower().endswith(".exe"):
            download_url = a.get("browser_download_url")
            asset_name = name
            asset_size = a.get("size", 0)
            if "noc" in name.lower():
                break

    has_update = is_newer_version(APP_VERSION, tag_name)

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


class DownloadUpdateWorker(QThread):
    """Threaded worker to download the update executable with progress reporting."""
    progress = pyqtSignal(int, int, float)   # (bytes_done, bytes_total, percent)
    download_finished = pyqtSignal(str)      # target_file_path
    download_failed = pyqtSignal(str)        # error_message

    def __init__(self, download_url: str, target_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.download_url = download_url
        self.target_path = Path(target_path)
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            self.target_path.parent.mkdir(parents=True, exist_ok=True)
            headers = {"User-Agent": f"NOCTools-Updater/{APP_VERSION}"}

            with requests.get(self.download_url, headers=headers, stream=True, timeout=15) as r:
                r.raise_for_status()
                total_size = int(r.headers.get("content-length", 0))
                downloaded = 0

                with open(self.target_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if self._cancelled:
                            f.close()
                            self.target_path.unlink(missing_ok=True)
                            return
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            pct = (downloaded / total_size * 100) if total_size > 0 else 0.0
                            self.progress.emit(downloaded, total_size, pct)

            self.download_finished.emit(str(self.target_path))
        except Exception as err:
            if self.target_path.exists():
                self.target_path.unlink(missing_ok=True)
            self.download_failed.emit(str(err))


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

        self.setWindowTitle(f"Pembaruan Aplikasi — {APP_NAME}")
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
        title_lbl = QLabel("Versi Baru Tersedia!")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: palette(text);")
        title_col.addWidget(title_lbl)

        tag = self.release_info.get("tag_name", "")
        rel_name = self.release_info.get("name", "")
        sub_text = f"Versi Anda: <b>v{APP_VERSION}</b>  ➔  Versi Terbaru: <b>{tag}</b>"
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

        # Changelog / Release Notes
        lbl_notes = QLabel("Catatan Perubahan (Changelog):")
        lbl_notes.setStyleSheet("font-weight: 600; font-size: 12px;")
        layout.addWidget(lbl_notes)

        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        raw_body = self.release_info.get("body", "Tidak ada catatan rilis.")
        # Basic markdown to HTML conversion for bullet points and headers
        formatted_body = raw_body.replace("\n", "<br>")
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

        # Action Buttons
        btn_layout = QHBoxLayout()

        self.btn_browser = QPushButton("🌐 Buka di GitHub")
        self.btn_browser.clicked.connect(self._open_in_browser)
        btn_layout.addWidget(self.btn_browser)

        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Nanti Saja")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        download_url = self.release_info.get("download_url")
        if download_url:
            self.btn_update = QPushButton("⚡ Update Sekarang")
            self.btn_update.setStyleSheet(
                "QPushButton { background-color: #0284C7; color: white; font-weight: bold; padding: 6px 16px; border-radius: 6px; }"
                "QPushButton:hover { background-color: #0369A1; }"
            )
            self.btn_update.clicked.connect(self._start_download)
            btn_layout.addWidget(self.btn_update)
        else:
            self.btn_update = None

        layout.addLayout(btn_layout)

    def _open_in_browser(self) -> None:
        url = self.release_info.get("html_url")
        if url:
            import webbrowser
            webbrowser.open(url)

    def _start_download(self) -> None:
        download_url = self.release_info.get("download_url")
        if not download_url:
            QMessageBox.warning(self, "Download Gagal", "File installer (.exe) tidak ditemukan pada rilis ini.")
            return

        # Prepare target file in Temp directory
        asset_name = self.release_info.get("asset_name") or f"{APP_NAME}_Update.exe"
        target_path = Path(tempfile.gettempdir()) / asset_name

        self.progress_bar.setVisible(True)
        self.status_lbl.setVisible(True)
        self.status_lbl.setText("Menghubungi server GitHub...")
        if self.btn_update:
            self.btn_update.setEnabled(False)
        self.btn_cancel.setText("Batal")

        self.download_worker = DownloadUpdateWorker(download_url, target_path, self)
        self.download_worker.progress.connect(self._on_progress)
        self.download_worker.download_finished.connect(self._on_download_complete)
        self.download_worker.download_failed.connect(self._on_download_error)
        self.download_worker.start()

    def _on_progress(self, downloaded: int, total: int, pct: float) -> None:
        self.progress_bar.setValue(int(pct))
        d_mb = downloaded / (1024 * 1024)
        t_mb = total / (1024 * 1024)
        if total > 0:
            self.status_lbl.setText(f"Mengunduh: {d_mb:.1f} MB / {t_mb:.1f} MB ({pct:.0f}%)")
        else:
            self.status_lbl.setText(f"Mengunduh: {d_mb:.1f} MB...")

    def _on_download_complete(self, target_path: str) -> None:
        self.status_lbl.setText("✅ Unduhan selesai! Memasang update...")
        self.progress_bar.setValue(100)

        # Confirm and restart
        msg = QMessageBox(self)
        msg.setWindowTitle("Update Siap Dipasang")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("File pembaruan berhasil diunduh.")
        msg.setInformativeText(
            "Aplikasi akan ditutup sementara dan dimulai ulang secara otomatis dengan versi terbaru.\n\n"
            "Lanjutkan proses restart?"
        )
        btn_now = msg.addButton("Restart & Update Sekarang", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Nanti Saja", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_now)
        msg.exec()

        if msg.clickedButton() == btn_now:
            apply_update_and_restart(target_path)
        else:
            self.accept()

    def _on_download_error(self, err_msg: str) -> None:
        self.status_lbl.setText(f"❌ Gagal: {err_msg}")
        QMessageBox.critical(self, "Gagal Mengunduh Update", f"Terjadi kesalahan saat mengunduh:\n\n{err_msg}")
        if self.btn_update:
            self.btn_update.setEnabled(True)
        self.btn_cancel.setText("Tutup")

    def reject(self) -> None:
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.cancel()
            self.download_worker.wait(1000)
        super().reject()
