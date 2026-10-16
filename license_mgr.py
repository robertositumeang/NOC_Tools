"""Verify Ed25519-signed, machine-bound NOC Tools licenses.

License payloads are authenticated but not encrypted. Expiration is checked
against the system clock, with a local last-seen timestamp for basic rollback
detection; that local state is not tamper-proof against a local administrator.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit, urlunsplit

import requests
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
from license_crypto import (
    ACTIVATION_PREFIX,
    LEGACY_LICENSE_PREFIX,
    LICENSE_PREFIX,
    LICENSE_PUBLIC_KEY,
    decode_signed_payload,
    normalize_email,
)

_LICENSE_PREFIX: Final[str] = LEGACY_LICENSE_PREFIX
_LICENSE_PUBLIC_KEY: Final[bytes] = LICENSE_PUBLIC_KEY

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


def _verify_signed_license_blob(license_key: str) -> dict:
    """Verify a signed license or activation token before parsing its payload."""
    clean_key = (license_key or "").strip()
    if clean_key.startswith(ACTIVATION_PREFIX):
        payload = decode_signed_payload(
            clean_key,
            prefix=ACTIVATION_PREFIX,
            public_key=_LICENSE_PUBLIC_KEY,
        )
        if payload.get("v") != 1 or payload.get("kind") != "activation":
            raise ValueError("Versi payload aktivasi tidak didukung.")
        return payload
    if clean_key.startswith(LICENSE_PREFIX):
        raise ValueError(
            "Lisensi ini belum diaktivasi online; hubungkan ke layanan aktivasi."
        )
    if not clean_key.startswith(_LICENSE_PREFIX):
        raise ValueError("Format lisensi tidak didukung; lisensi harus diterbitkan ulang.")
    payload = decode_signed_payload(
        clean_key,
        prefix=_LICENSE_PREFIX,
        public_key=_LICENSE_PUBLIC_KEY,
    )
    if payload.get("v") != 2:
        raise ValueError("Versi payload lisensi tidak didukung.")
    return payload


def verify_license_key(key_str: str) -> tuple[bool, str, int, str]:
    """Verify license authenticity, machine binding, anti-clock-rollback, and expiration date.

    Returns:
        (is_valid: bool, status_msg: str, days_left: int, expiry_date_str: str)
    """
    clean_key = (key_str or "").strip()
    if not clean_key:
        return False, "License Key belum dimasukkan.", 0, ""

    try:
        payload = _verify_signed_license_blob(clean_key)
        lic_mid = payload.get("mid")
        exp_epoch = payload.get("exp")
        issued_epoch = payload.get("iat")
        lic_type = payload.get("type")
        is_activation = payload.get("kind") == "activation"
        if (
            not isinstance(lic_mid, str)
            or not isinstance(exp_epoch, int)
            or isinstance(exp_epoch, bool)
            or not isinstance(issued_epoch, int)
            or isinstance(issued_epoch, bool)
            or not isinstance(lic_type, str)
            or not lic_mid
            or exp_epoch <= issued_epoch
        ):
            raise ValueError("Payload lisensi tidak valid.")
        lic_mid = lic_mid.strip().upper()
        if is_activation:
            if not isinstance(payload.get("jti"), str) or not payload["jti"]:
                raise ValueError("Payload aktivasi tidak valid.")
            normalize_email(payload.get("email", ""))
        elif not clean_key.startswith(_LICENSE_PREFIX):
            raise ValueError("Payload aktivasi tidak valid.")

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


def _verify_issued_license(email: str, machine_id: str, license_key: str) -> dict:
    normalized_email = normalize_email(email)
    payload = decode_signed_payload(
        license_key.strip(),
        prefix=LICENSE_PREFIX,
        public_key=_LICENSE_PUBLIC_KEY,
    )
    days_valid = payload.get("days")
    issued_at = payload.get("iat")
    if (
        payload.get("v") != 3
        or payload.get("email") != normalized_email
        or payload.get("mid") != machine_id.strip().upper()
        or not isinstance(days_valid, int)
        or isinstance(days_valid, bool)
        or days_valid <= 0
        or not isinstance(issued_at, int)
        or isinstance(issued_at, bool)
        or not isinstance(payload.get("jti"), str)
        or not payload["jti"]
    ):
        raise ValueError("Email, Machine ID, atau payload tidak cocok dengan lisensi.")
    return payload


def activate_license_online(
    email: str,
    license_key: str,
    machine_id: str,
    *,
    api_url: str | None = None,
    ca_bundle: str | None = None,
) -> str:
    """Redeem a signed license once and return its signed offline activation token."""
    normalized_email = normalize_email(email)
    clean_machine_id = machine_id.strip().upper()
    issued_payload = _verify_issued_license(
        normalized_email,
        clean_machine_id,
        license_key,
    )
    activation_api_url = (api_url or os.environ.get("NOC_LICENSE_API_URL", "")).strip()
    if not activation_api_url:
        raise ValueError("URL layanan aktivasi belum dikonfigurasi.")

    parsed_url = urlsplit(activation_api_url)
    configured_ca_bundle = (
        ca_bundle
        or os.environ.get("NOC_LICENSE_API_CA_BUNDLE")
        or True
    )
    local_http_allowed = parsed_url.scheme == "http" and parsed_url.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }
    if (
        not parsed_url.hostname
        or parsed_url.username
        or parsed_url.password
        or parsed_url.query
        or parsed_url.fragment
        or (parsed_url.scheme != "https" and not local_http_allowed)
    ):
        raise ValueError(
            "URL layanan aktivasi harus menggunakan HTTPS; HTTP hanya diizinkan untuk localhost."
        )

    endpoint = urlunsplit(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            f"{parsed_url.path.rstrip('/')}/v1/activate",
            "",
            "",
        )
    )
    try:
        response = requests.post(
            endpoint,
            json={
                "email": normalized_email,
                "license_key": license_key.strip(),
                "machine_id": clean_machine_id,
            },
            timeout=(5, 15),
            verify=configured_ca_bundle,
        )
    except requests.RequestException as exc:
        raise ValueError(f"Tidak dapat menghubungi layanan aktivasi: {exc}") from exc

    if not response.ok:
        try:
            error_detail = response.json().get("detail", "")
        except (ValueError, AttributeError):
            error_detail = ""
        if not isinstance(error_detail, str):
            error_detail = ""
        raise ValueError(
            error_detail or f"Layanan aktivasi menolak permintaan (HTTP {response.status_code})."
        )

    try:
        response_data = response.json()
    except ValueError as exc:
        raise ValueError("Respons layanan aktivasi tidak valid.") from exc

    if not isinstance(response_data, dict):
        raise ValueError("Respons layanan aktivasi tidak valid.")
    activation_token = response_data.get("activation_token")
    if not isinstance(activation_token, str) or not activation_token:
        raise ValueError("Respons layanan aktivasi tidak memuat bukti aktivasi.")
    activation_payload = _verify_signed_license_blob(activation_token)
    if (
        activation_payload.get("email") != normalized_email
        or activation_payload.get("mid") != clean_machine_id
        or activation_payload.get("jti") != issued_payload.get("jti")
    ):
        raise ValueError("Bukti aktivasi tidak cocok dengan permintaan lisensi.")
    is_valid, message, _, _ = verify_license_key(activation_token)
    if not is_valid:
        raise ValueError(message)
    return activation_token


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
        self.setFixedSize(540, 640)
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

        subtitle = QLabel("PT. KEREAKTIF Indonesia  ·  ENTERPRISE NOC")
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

        hint_mid = QLabel("Berikan Machine ID dan email Anda kepada Administrator untuk penerbitan lisensi.")
        hint_mid.setStyleSheet("color: #64748B; font-size: 10px;")
        hint_mid.setWordWrap(True)
        c_layout.addWidget(hint_mid)

        c_layout.addSpacing(6)

        lbl_email = QLabel("EMAIL PENGGUNA:")
        lbl_email.setObjectName("fieldLabel")
        c_layout.addWidget(lbl_email)

        self.txt_email = QLineEdit()
        self.txt_email.setPlaceholderText("nama@perusahaan.com")
        self.txt_email.setClearButtonEnabled(True)
        c_layout.addWidget(self.txt_email)

        # License Key Input Section
        lbl_key = QLabel("MASUKKAN LICENSE KEY:")
        lbl_key.setObjectName("fieldLabel")
        c_layout.addWidget(lbl_key)

        self.txt_key = QLineEdit()
        self.txt_key.setPlaceholderText("NOC-LIC3-...")
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
        footer = QLabel("🛡️ Email-Bound · Hardware-Bound · Aktivasi Online, validasi offline")
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
        email = self.txt_email.text().strip()
        raw_key = self.txt_key.text().strip()
        if not email:
            self.lbl_status.setStyleSheet("color: #FB7185;")
            self.lbl_status.setText("Mohon masukkan email pengguna.")
            self.lbl_status.setVisible(True)
            return
        if not raw_key:
            self.lbl_status.setStyleSheet("color: #FB7185;")
            self.lbl_status.setText("Mohon masukkan License Key.")
            self.lbl_status.setVisible(True)
            return

        try:
            activation_token = activate_license_online(
                email,
                raw_key,
                self.machine_id,
            )
        except ValueError as error:
            self.lbl_status.setStyleSheet("color: #FB7185;")
            self.lbl_status.setText(f"❌ {error}")
            self.lbl_status.setVisible(True)
            return

        is_valid, msg, days_left, exp_date = verify_license_key(activation_token)
        if is_valid and save_license(activation_token):
            self.is_activated = True
            QMessageBox.information(
                self,
                "Aktivasi Berhasil",
                f"<b>Lisensi Berhasil Diaktifkan!</b><br><br>"
                f"Status: <b>{msg}</b><br>"
                f"Masa berlaku: <b>{days_left} hari</b> (sampai {exp_date}).<br>"
                f"Email: <b>{email}</b><br>"
                f"Perangkat: <b>{self.machine_id}</b>",
            )
            self.accept()
        else:
            self.lbl_status.setStyleSheet("color: #FB7185;")
            detail = msg if not is_valid else "Lisensi aktif, tetapi tidak dapat disimpan."
            self.lbl_status.setText(f"❌ {detail}")
            self.lbl_status.setVisible(True)
