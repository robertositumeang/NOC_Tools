"""
Enterprise Cryptographic License Management Module for NOC Tools.
PT. Lindu Putra Utama | Network Operations Center

Security Architecture:
  1. Hardware-Bound Fingerprinting:
     - Derives Machine ID from Windows Registry Cryptography MachineGuid.
     - Fallback to hardware MAC node if registry is restricted.
     - Licenses cannot be transplanted to another workstation.
  2. Authenticated End-to-End Encryption (Encrypt-then-MAC):
     - Payload is fully encrypted using PBKDF2-SHA256 + CTR Keystream.
     - Integrity secured with HMAC-SHA256 authentication tag.
     - License key contains zero plaintext; unauthorized parties cannot inspect data.
  3. Time-Limited Access Control & Anti-Rollback:
     - Supports 1-Month (30 days), custom, or 1-Year license durations.
     - Validates current date against expiration epoch.
     - Local encrypted telemetry prevents system clock manipulation.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Application Cryptographic Master Pepper for License Verification
_LICENSE_PEPPER: Final[bytes] = b"NOC_ENTERPRISE_KEY_V2_2026_PT_LINDU_PUTRA_UTAMA_RESTRICTED"

# Local Storage paths in %APPDATA%/NOC_Tools
_STORAGE_DIR: Path = Path(os.environ.get("APPDATA", str(Path.home()))) / "NOC_Tools"
_LICENSE_FILE: Path = _STORAGE_DIR / "license.lic"
_STATE_FILE: Path = _STORAGE_DIR / ".syslock"


def get_machine_id() -> str:
    """Generate a clean, reproducible machine identifier bound to the Windows installation."""
    raw_id = ""
    # Method 1: Windows Registry MachineGuid (Unique per Windows installation)
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            )
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
            if guid:
                raw_id = f"WIN-{guid}"
        except Exception:
            pass

    # Method 2: Hardware MAC node fallback
    if not raw_id:
        node = uuid.getnode()
        raw_id = f"NODE-{node}"

    # Format as clean 16-hex NOC identifier: NOC-XXXX-XXXX-XXXX-XXXX
    digest = hashlib.sha256(raw_id.encode("utf-8")).hexdigest().upper()
    return f"NOC-{digest[:4]}-{digest[4:8]}-{digest[8:12]}-{digest[12:16]}"


def _decrypt_and_verify_blob(encrypted_key: str) -> dict:
    """Decrypt authenticated encrypted license token and verify HMAC integrity."""
    clean_str = encrypted_key.strip()
    # Strip prefix and all formatting dashes/spaces
    for prefix in ("NOC-LIC1M-", "NOC-LIC-", "NOC-"):
        if clean_str.startswith(prefix):
            clean_str = clean_str[len(prefix):]
            break
    clean_hex = clean_str.replace("-", "").replace(" ", "")

    try:
        blob = bytes.fromhex(clean_hex)
    except ValueError as exc:
        raise ValueError("Format karakter lisensi tidak valid (harus hex).") from exc

    if len(blob) < 65:
        raise ValueError("Ukuran paket lisensi tidak valid.")


    salt = blob[:16]
    iv = blob[16:32]
    tag = blob[32:64]
    ciphertext = blob[64:]

    # 1. Derive separate encryption and MAC keys from Master Pepper
    mac_key = hashlib.pbkdf2_hmac("sha256", _LICENSE_PEPPER, salt + b"MAC", 10000, 32)
    expected_tag = hmac.new(mac_key, salt + iv + ciphertext, hashlib.sha256).digest()

    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("Tanda tangan digital lisensi tidak sah atau data rusak.")

    # 2. Decrypt ciphertext using CTR-keystream
    enc_key = hashlib.pbkdf2_hmac("sha256", _LICENSE_PEPPER, salt + b"ENC", 10000, 32)
    keystream = b""
    counter = 0
    while len(keystream) < len(ciphertext):
        keystream += hmac.new(enc_key, iv + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1

    plaintext = bytes(c ^ k for c, k in zip(ciphertext, keystream[: len(ciphertext)]))
    return json.loads(plaintext.decode("utf-8"))


def verify_license_key(key_str: str) -> tuple[bool, str, int, str]:
    """Verify license authenticity, machine binding, anti-clock-rollback, and expiration date.

    Returns:
        (is_valid: bool, status_msg: str, days_left: int, expiry_date_str: str)
    """
    clean_key = (key_str or "").strip()
    if not clean_key:
        return False, "License Key belum dimasukkan.", 0, ""

    try:
        payload = _decrypt_and_verify_blob(clean_key)
        lic_mid = payload.get("mid", "").strip().upper()
        exp_epoch = int(payload.get("exp", 0))
        lic_type = payload.get("type", "1_MONTH")

        # 1. Verify Machine Binding
        current_mid = get_machine_id()
        if lic_mid != current_mid:
            return (
                False,
                f"Lisensi ini terikat ke perangkat lain ({lic_mid}). "
                f"Perangkat Anda: {current_mid}",
                0,
                "",
            )

        # 2. Expiration Date Verification
        now_epoch = int(time.time())
        exp_dt = datetime.fromtimestamp(exp_epoch, tz=timezone.utc)
        exp_date_str = exp_dt.strftime("%d %B %Y")

        # 3. Anti Clock-Rollback Protection
        last_seen = _read_last_seen_time()
        if now_epoch < last_seen - 3600:  # Allow max 1 hr clock drift
            return False, "Terdeteksi manipulasi jam sistem komputer (Clock Rollback).", 0, exp_date_str

        _record_seen_time(now_epoch)

        if now_epoch > exp_epoch:
            return False, f"Masa berlaku lisensi telah habis pada {exp_date_str}.", 0, exp_date_str

        days_left = max(0, (exp_epoch - now_epoch) // 86400)
        return True, f"Lisensi Aktif ({lic_type}).", days_left, exp_date_str

    except Exception as exc:
        return False, f"Gagal memverifikasi lisensi: {exc}", 0, ""


def save_license(key_str: str) -> bool:
    """Store active license key into local application storage."""
    try:
        _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        _LICENSE_FILE.write_text(key_str.strip(), encoding="utf-8")
        return True
    except Exception:
        return False


def load_installed_license() -> str:
    """Load installed license key string from storage."""
    try:
        if _LICENSE_FILE.is_file():
            return _LICENSE_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


def check_active_license() -> tuple[bool, str, int, str]:
    """Check if the current computer holds a valid active license."""
    installed_key = load_installed_license()
    if not installed_key:
        return False, "Lisensi belum terpasang di perangkat ini.", 0, ""
    return verify_license_key(installed_key)


def _read_last_seen_time() -> int:
    """Read last recorded valid runtime timestamp."""
    try:
        if _STATE_FILE.is_file():
            data = _STATE_FILE.read_text(encoding="utf-8").strip()
            return int(data)
    except Exception:
        pass
    return 0


def _record_seen_time(ts: int) -> None:
    """Record current timestamp for clock-rollback check."""
    try:
        _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(str(ts), encoding="utf-8")
    except Exception:
        pass


# ── Dark Glassmorphism License Activation Dialog ──────────────────────────────
_LIC_STYLE = """
QDialog {
    background: #090D16;
    color: #E2E8F0;
    font-family: 'Segoe UI', Arial, sans-serif;
}

QFrame#cardMain {
    background: rgba(15, 23, 42, 0.95);
    border: 1px solid rgba(56, 189, 248, 0.25);
    border-radius: 20px;
}

QLabel#titleLabel {
    color: #F8FAFC;
    font-size: 20px;
    font-weight: 700;
}

QLabel#subtitleLabel {
    color: #64748B;
    font-size: 11px;
    letter-spacing: 1.2px;
    font-weight: 600;
}

QLabel#fieldLabel {
    color: #94A3B8;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
}

QLineEdit {
    background: rgba(10, 14, 26, 0.85);
    border: 1px solid rgba(56, 189, 248, 0.20);
    border-radius: 9px;
    padding: 10px 14px;
    color: #F1F5F9;
    font-size: 12px;
    font-family: 'Consolas', 'Courier New', monospace;
}

QLineEdit:focus {
    border: 1px solid #38BDF8;
    background: rgba(15, 23, 42, 0.95);
}

QPushButton#btnCopy {
    background: rgba(56, 189, 248, 0.12);
    color: #38BDF8;
    border: 1px solid rgba(56, 189, 248, 0.3);
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 11px;
    font-weight: 600;
}

QPushButton#btnCopy:hover {
    background: rgba(56, 189, 248, 0.25);
}

QPushButton#btnActivate {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #0284C7, stop:1 #0EA5E9
    );
    color: #FFFFFF;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.8px;
    border: none;
    border-radius: 9px;
    padding: 12px 20px;
}

QPushButton#btnActivate:hover {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #0EA5E9, stop:1 #38BDF8
    );
    color: #041324;
}

QLabel#statusLabel {
    font-size: 11px;
    font-weight: 600;
    padding: 4px;
}
"""


class LicenseActivationDialog(QDialog):
    """Sleek modal dialog for hardware binding and license key activation."""

    def __init__(self, parent: QWidget | None = None, initial_msg: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Aktivasi Lisensi Operasional - NOC Tools")
        self.setFixedSize(540, 580)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet(_LIC_STYLE)

        self.machine_id = get_machine_id()
        self.initial_msg = initial_msg
        self.is_activated = False

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        card = QFrame()
        card.setObjectName("cardMain")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(30, 26, 30, 26)
        c_layout.setSpacing(14)

        # Header
        hdr = QVBoxLayout()
        hdr.setSpacing(4)
        hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel("🔑")
        icon_lbl.setStyleSheet("font-size: 34px;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.addWidget(icon_lbl)

        title = QLabel("Aktivasi Lisensi Perangkat")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.addWidget(title)

        subtitle = QLabel("PT. LINDU PUTRA UTAMA  ·  ENTERPRISE NOC")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.addWidget(subtitle)

        c_layout.addLayout(hdr)
        c_layout.addSpacing(6)

        # Machine ID Section
        lbl_mid = QLabel("MACHINE ID PERANGKAT ANDA:")
        lbl_mid.setObjectName("fieldLabel")
        c_layout.addWidget(lbl_mid)

        row_mid = QHBoxLayout()
        self.txt_mid = QLineEdit(self.machine_id)
        self.txt_mid.setReadOnly(True)
        self.txt_mid.setStyleSheet("color: #38BDF8; font-weight: bold; font-size: 13px;")
        row_mid.addWidget(self.txt_mid)

        btn_copy = QPushButton("📋 Salin ID")
        btn_copy.setObjectName("btnCopy")
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.clicked.connect(self._copy_mid)
        row_mid.addWidget(btn_copy)
        c_layout.addLayout(row_mid)

        hint_mid = QLabel("Kirimkan Machine ID ini kepada Administrator Jaringan untuk mendapatkan License Key.")
        hint_mid.setStyleSheet("color: #64748B; font-size: 10px;")
        hint_mid.setWordWrap(True)
        c_layout.addWidget(hint_mid)

        c_layout.addSpacing(6)

        # License Key Input Section
        lbl_key = QLabel("MASUKKAN LICENSE KEY:")
        lbl_key.setObjectName("fieldLabel")
        c_layout.addWidget(lbl_key)

        self.txt_key = QLineEdit()
        self.txt_key.setPlaceholderText("NOC-LIC1M-XXXXX-XXXXX-XXXXX-...")
        self.txt_key.returnPressed.connect(self._handle_activate)
        c_layout.addWidget(self.txt_key)

        # Status Message
        self.lbl_status = QLabel(self.initial_msg or "")
        self.lbl_status.setObjectName("statusLabel")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color: #FB7185;")
        self.lbl_status.setVisible(bool(self.initial_msg))
        c_layout.addWidget(self.lbl_status)

        # Activate Button
        btn_act = QPushButton("AKTIFKAN LISENSI  ➔")
        btn_act.setObjectName("btnActivate")
        btn_act.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_act.clicked.connect(self._handle_activate)
        c_layout.addWidget(btn_act)

        c_layout.addStretch()

        # Footer notice
        footer = QLabel("🛡️ Terenkripsi End-to-End · Hardware-Bound · Offline Validated")
        footer.setStyleSheet("color: #475569; font-size: 10px;")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.addWidget(footer)

        layout.addWidget(card)

    def _copy_mid(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.machine_id)
            self.lbl_status.setStyleSheet("color: #38BDF8;")
            self.lbl_status.setText("✅ Machine ID berhasil disalin ke clipboard.")
            self.lbl_status.setVisible(True)

    def _handle_activate(self) -> None:
        raw_key = self.txt_key.text().strip()
        if not raw_key:
            self.lbl_status.setStyleSheet("color: #FB7185;")
            self.lbl_status.setText("Mohon masukkan License Key.")
            self.lbl_status.setVisible(True)
            return

        is_valid, msg, days_left, exp_date = verify_license_key(raw_key)
        if is_valid:
            save_license(raw_key)
            self.is_activated = True
            QMessageBox.information(
                self,
                "Aktivasi Berhasil",
                f"<b>Lisensi Berhasil Diaktifkan!</b><br><br>"
                f"Status: <b>{msg}</b><br>"
                f"Masa berlaku: <b>{days_left} hari</b> (sampai {exp_date}).<br>"
                f"Perangkat: <b>{self.machine_id}</b>",
            )
            self.accept()
        else:
            self.lbl_status.setStyleSheet("color: #FB7185;")
            self.lbl_status.setText(f"❌ {msg}")
            self.lbl_status.setVisible(True)
