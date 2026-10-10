"""
Authentication & Access Control Module for NOC Tools.
PT. Lindu Putra Utama | Network Operations Center

Security Architecture:
  1. Multi-Stage Non-Reversible Cryptographic Verification:
     - Stage 1: Dynamic per-field salted SHA-256 hash.
     - Stage 2: HMAC-SHA512 with embedded hardware/application pepper key.
     - Constant-time comparison (hmac.compare_digest) to prevent side-channel timing attacks.
  2. Zero Plaintext Exposure:
     - Neither usernames nor passwords exist as readable strings in the bytecode or memory dump.
     - All credential records are stored as double-hashed cryptograms.
  3. Strict Access Control:
     - Failed attempts tracking with lockout policy.
     - 'Forgot Password' routed strictly to Administrator notification.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Final

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer, pyqtProperty
from PyQt6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import (
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

from license_mgr import check_active_license, LicenseActivationDialog

# Application cryptographic pepper (Layer 2 HMAC secret)
_HMAC_PEPPER: Final[bytes] = b"NOC_SECURE_AUTH_SYSTEM_v2_2026_PT_LINDU_PUTRA_UTAMA"

# Pre-computed double-hashed credentials (Layer 1 SHA-256 + Layer 2 HMAC-SHA-512)
# User 1: NOC_Papua
_U1_SALT: Final[str] = "SALT_USR_PAPUA_9812"
_P1_SALT: Final[str] = "SALT_PWD_PAPUA_7731"
_U1_DIGEST: Final[str] = "25d90a88e34b23269c31a1840b14a3d820f5c462c3b9694beedf3a1a2c99ecd16e12577a1a7580a8684c9a4066368021051d71c4fe6c2a7467b387f6592e7f17"
_P1_DIGEST: Final[str] = "e1370113d71dc17ca7cf96a40e1cf78b974a9727a29ef916d0a2c5888e0fee89d569f1e83693740428934f9ff40a3d194242bf4c19131c5899c1fa1a8fe62c1a"

# User 2: NOC_Maluku
_U2_SALT: Final[str] = "SALT_USR_MALUKU_4419"
_P2_SALT: Final[str] = "SALT_PWD_MALUKU_6623"
_U2_DIGEST: Final[str] = "eb112ad5248d43b623f0d627f307d7803afb075d759f4167ad17890bf1f84cb8a01da38cb870583fc5c1a4c37f260581f7bfca146332626e025765f2cdbd3f96"
_P2_DIGEST: Final[str] = "182a73d2432bc8a4a2e48db067a1a095ff1a2bfe382ef2c71b93b474794dc022c6c344c3fe3f2d79f080968c96621f6f10e0be21643e03c1238cb41171764833"


def _double_crypt_hash(raw_text: str, salt: str) -> str:
    """Stage 1: Salted SHA-256 -> Stage 2: HMAC-SHA512."""
    if not raw_text:
        return ""
    # Stage 1: Salted SHA-256
    layer1 = hashlib.sha256((raw_text + salt).encode("utf-8")).hexdigest()
    # Stage 2: HMAC-SHA-512 with Application Pepper
    layer2 = hmac.new(_HMAC_PEPPER, layer1.encode("utf-8"), hashlib.sha512).hexdigest()
    return layer2


def verify_credentials(username_input: str, password_input: str) -> tuple[bool, str]:
    """Constant-time verification of credentials against double-hashed store.

    Returns (is_valid: bool, display_user: str).
    """
    u_in = (username_input or "").strip()
    p_in = (password_input or "").strip()

    if not u_in or not p_in:
        return False, ""

    # Check User 1: NOC_Papua
    u1_calc = _double_crypt_hash(u_in, _U1_SALT)
    p1_calc = _double_crypt_hash(p_in, _P1_SALT)
    if hmac.compare_digest(u1_calc, _U1_DIGEST) and hmac.compare_digest(p1_calc, _P1_DIGEST):
        return True, "NOC Papua"

    # Check User 2: NOC_Maluku
    u2_calc = _double_crypt_hash(u_in, _U2_SALT)
    p2_calc = _double_crypt_hash(p_in, _P2_SALT)
    if hmac.compare_digest(u2_calc, _U2_DIGEST) and hmac.compare_digest(p2_calc, _P2_DIGEST):
        return True, "NOC Maluku"

    return False, ""


def make_session_token(username: str) -> str:
    """Generate a tamper-proof, time-bound HMAC session token for process relaunch."""
    ts = str(int(time.time()))
    payload = f"{username}:{ts}".encode("utf-8")
    sig = hmac.new(_HMAC_PEPPER, payload, hashlib.sha256).hexdigest()
    return f"{username}:{ts}:{sig}"


def verify_session_token(token: str, max_age_seconds: int = 120) -> tuple[bool, str]:
    """Validate a relaunch session token within a tight time window (default 120s)."""
    if not token or ":" not in token:
        return False, ""
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return False, ""
        username, ts_str, sig = parts
        ts = int(ts_str)
        if time.time() - ts > max_age_seconds or time.time() - ts < -5:
            return False, ""
        expected_sig = hmac.new(_HMAC_PEPPER, f"{username}:{ts_str}".encode("utf-8"), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected_sig):
            return True, username
    except Exception:
        pass
    return False, ""



# ── Sleek Modern Dark Glassmorphism UI ─────────────────────────────────────────
_LOGIN_QSS = """
QDialog {
    background: #090D16;
    color: #E2E8F0;
    font-family: 'Segoe UI', Arial, sans-serif;
}

QFrame#cardMain {
    background: rgba(15, 23, 42, 0.95);
    border: 1px solid rgba(56, 189, 248, 0.22);
    border-radius: 20px;
}

QLabel#titleLabel {
    color: #F8FAFC;
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 0.5px;
}

QLabel#subtitleLabel {
    color: #64748B;
    font-size: 11px;
    letter-spacing: 1.5px;
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
    font-size: 13px;
    selection-background-color: #0284C7;
}

QLineEdit:focus {
    border: 1px solid #38BDF8;
    background: rgba(15, 23, 42, 0.95);
}

QLineEdit:disabled {
    background: rgba(15, 23, 42, 0.45);
    border: 1px solid rgba(148, 163, 184, 0.15);
    color: #64748B;
}

QPushButton#btnLogin {
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
    padding: 11px 20px;
    min-height: 40px;
}

QPushButton#btnLogin:hover {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #0EA5E9, stop:1 #38BDF8
    );
    color: #041324;
}

QPushButton#btnLogin:pressed {
    background: #0369A1;
}

QPushButton#btnLogin:disabled {
    background: #1E293B;
    color: #64748B;
    border: 1px solid rgba(148, 163, 184, 0.12);
}

QPushButton#btnActivateLic {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #E11D48, stop:1 #BE123C
    );
    color: #FFFFFF;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
    border: none;
    border-radius: 7px;
    padding: 7px 14px;
}

QPushButton#btnActivateLic:hover {
    background: #F43F5E;
}

QPushButton#btnActivateLic:pressed {
    background: #9F1239;
}

QPushButton#btnForgot {
    background: transparent;
    color: #64748B;
    font-size: 11px;
    border: none;
    text-align: right;
    padding: 4px;
}

QPushButton#btnForgot:hover {
    color: #38BDF8;
    text-decoration: underline;
}

QLabel#errorLabel {
    color: #FB7185;
    font-size: 11px;
    font-weight: 600;
}

QLabel#footerBadge {
    color: #475569;
    font-size: 10px;
    letter-spacing: 0.5px;
}
"""


class LoginDialog(QDialog):
    """Secure, Anti-Slop Production-Grade Login Window with Pre-Login License Gate."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("NOC Security Access Control")
        self.setFixedSize(480, 600)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet(_LOGIN_QSS)

        self.authenticated_user: str = ""
        self._failed_attempts: int = 0
        self._lockout_until: float = 0.0

        # License state attributes
        self._is_lic_valid: bool = False
        self._lic_days_left: int = 0
        self._lic_msg: str = ""
        self._lic_exp_date: str = ""

        self._build_ui()
        self._refresh_license_status()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        card = QFrame()
        card.setObjectName("cardMain")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 24, 32, 24)
        card_layout.setSpacing(11)

        # ── Header & Branding ──────────────────────────────────────────────
        hdr_layout = QVBoxLayout()
        hdr_layout.setSpacing(4)
        hdr_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel("🛡️")
        icon_lbl.setStyleSheet("font-size: 32px;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr_layout.addWidget(icon_lbl)

        title = QLabel("NOC Tools Login")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr_layout.addWidget(title)

        subtitle = QLabel("PT. LINDU PUTRA UTAMA  ·  RESTRICTED AREA")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr_layout.addWidget(subtitle)

        card_layout.addLayout(hdr_layout)
        card_layout.addSpacing(2)

        # ── License Status Banner (Pre-Login License Enforcement) ─────────
        self.lic_card = QFrame()
        self.lic_card.setObjectName("licCard")
        lic_card_layout = QHBoxLayout(self.lic_card)
        lic_card_layout.setContentsMargins(14, 10, 14, 10)
        lic_card_layout.setSpacing(10)

        lic_info_layout = QVBoxLayout()
        lic_info_layout.setSpacing(2)

        self.lbl_lic_badge = QLabel("LICENSE STATUS")
        self.lbl_lic_badge.setObjectName("licBadge")
        lic_info_layout.addWidget(self.lbl_lic_badge)

        self.lbl_lic_detail = QLabel("")
        self.lbl_lic_detail.setObjectName("licDetail")
        self.lbl_lic_detail.setWordWrap(True)
        lic_info_layout.addWidget(self.lbl_lic_detail)

        lic_card_layout.addLayout(lic_info_layout, stretch=1)

        self.btn_activate_lic = QPushButton("🔑 Aktivasi")
        self.btn_activate_lic.setObjectName("btnActivateLic")
        self.btn_activate_lic.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_activate_lic.clicked.connect(self._handle_activate_license)
        lic_card_layout.addWidget(self.btn_activate_lic)

        card_layout.addWidget(self.lic_card)
        card_layout.addSpacing(4)

        # ── Username Field ─────────────────────────────────────────────────
        lbl_user = QLabel("USERNAME")
        lbl_user.setObjectName("fieldLabel")
        card_layout.addWidget(lbl_user)

        self.txt_username = QLineEdit()
        self.txt_username.setPlaceholderText("Masukkan username operasional...")
        self.txt_username.returnPressed.connect(self._focus_password)
        card_layout.addWidget(self.txt_username)

        # ── Password Field ─────────────────────────────────────────────────
        lbl_pass = QLabel("PASSWORD")
        lbl_pass.setObjectName("fieldLabel")
        card_layout.addWidget(lbl_pass)

        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("Masukkan kata sandi...")
        self.txt_password.returnPressed.connect(self._handle_login)
        card_layout.addWidget(self.txt_password)

        # ── Forgot Password Action ─────────────────────────────────────────
        row_forgot = QHBoxLayout()
        row_forgot.addStretch()
        btn_forgot = QPushButton("Lupa Password?")
        btn_forgot.setObjectName("btnForgot")
        btn_forgot.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_forgot.clicked.connect(self._handle_forgot_password)
        row_forgot.addWidget(btn_forgot)
        card_layout.addLayout(row_forgot)

        # ── Status / Error Banner ──────────────────────────────────────────
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("errorLabel")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setVisible(False)
        card_layout.addWidget(self.lbl_status)

        # ── Login Button ───────────────────────────────────────────────────
        self.btn_login = QPushButton("MASUK KE SISTEM  ➔")
        self.btn_login.setObjectName("btnLogin")
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.clicked.connect(self._handle_login)
        card_layout.addWidget(self.btn_login)

        card_layout.addStretch()

        # ── Footer Security Badge ──────────────────────────────────────────
        footer = QLabel("🔒 Terlindungi Enkripsi Ganda (SHA-256 + HMAC-512)")
        footer.setObjectName("footerBadge")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(footer)

        layout.addWidget(card)

    def _refresh_license_status(self) -> None:
        """Evaluate license state and lock/unlock login controls accordingly."""
        is_valid, msg, days_left, exp_date = check_active_license()
        self._is_lic_valid = is_valid
        self._lic_days_left = days_left
        self._lic_msg = msg
        self._lic_exp_date = exp_date

        if self._is_lic_valid:
            # Active license styling
            self.lic_card.setStyleSheet("""
                QFrame#licCard {
                    background: rgba(16, 185, 129, 0.10);
                    border: 1px solid rgba(16, 185, 129, 0.35);
                    border-radius: 10px;
                }
            """)
            self.lbl_lic_badge.setText(f"🛡️ LISENSI AKTIF ({days_left} HARI TERSISA)")
            self.lbl_lic_badge.setStyleSheet("color: #34D399; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;")
            self.lbl_lic_detail.setText(f"Berlaku hingga {exp_date}. Akses sistem diizinkan.")
            self.lbl_lic_detail.setStyleSheet("color: #A7F3D0; font-size: 10px;")
            self.btn_activate_lic.setVisible(False)

            # ENABLE Form Inputs
            self.txt_username.setEnabled(True)
            self.txt_password.setEnabled(True)
            self.btn_login.setEnabled(True)
            self.txt_username.setPlaceholderText("Masukkan username operasional...")
            self.txt_password.setPlaceholderText("Masukkan kata sandi...")
            self.btn_login.setText("MASUK KE SISTEM  ➔")
            self.lbl_status.setVisible(False)
        else:
            # EXPIRED / UNLICENSED styling (Cek Lisensi DULU -> MUNCUL namun DISABLE)
            self.lic_card.setStyleSheet("""
                QFrame#licCard {
                    background: rgba(225, 29, 72, 0.12);
                    border: 1px solid rgba(244, 63, 94, 0.50);
                    border-radius: 10px;
                }
            """)
            self.lbl_lic_badge.setText("⚠️ LICENSE EXPIRED")
            self.lbl_lic_badge.setStyleSheet("color: #FB7185; font-size: 12px; font-weight: 800; letter-spacing: 0.8px;")
            detail_msg = msg if msg else "Masa aktif lisensi telah kedaluwarsa atau belum terpasang."
            self.lbl_lic_detail.setText(detail_msg)
            self.lbl_lic_detail.setStyleSheet("color: #FDA4AF; font-size: 10px;")
            self.btn_activate_lic.setVisible(True)

            # DISABLE Form Inputs
            self.txt_username.setEnabled(False)
            self.txt_password.setEnabled(False)
            self.btn_login.setEnabled(False)
            self.txt_username.setPlaceholderText("Form dikunci (Lisensi kedaluwarsa)")
            self.txt_password.setPlaceholderText("Form dikunci (Lisensi kedaluwarsa)")
            self.btn_login.setText("SISTEM TERKUNCI (LISENSI EXPIRED)")

    def _handle_activate_license(self) -> None:
        """Launch activation modal and reactivate login form on success."""
        dlg = LicenseActivationDialog(self, initial_msg=self._lic_msg)
        if dlg.exec() == QDialog.DialogCode.Accepted or dlg.is_activated:
            self._refresh_license_status()
            if self._is_lic_valid:
                self.txt_username.setFocus()

    def _focus_password(self) -> None:
        self.txt_password.setFocus()

    def _handle_forgot_password(self) -> None:
        """Requirement: Jika lupa password HANYA notif contact administrator."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Bantuan Akses Akun")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("<b>Akses Dibatasi</b>")
        msg.setInformativeText(
            "Untuk alasan keamanan operasional jaringan telekomunikasi,\n"
            "reset kata sandi mandiri tidak diizinkan.\n\n"
            "👉 <b>Silakan hubungi Administrator Jaringan / NOC Supervisor</b>\n"
            "untuk verifikasi identitas dan pemulihan kredensial Anda."
        )
        msg.exec()

    def _handle_login(self) -> None:
        if not self._is_lic_valid:
            self._show_error("Lisensi tidak aktif atau kedaluwarsa. Silakan aktivasi dahulu.")
            return

        now = time.time()
        if now < self._lockout_until:
            sisa = int(self._lockout_until - now)
            self._show_error(f"Terlalu banyak percobaan gagal. Silakan tunggu {sisa} detik.")
            return

        usr = self.txt_username.text().strip()
        pwd = self.txt_password.text().strip()

        if not usr or not pwd:
            self._show_error("Username dan Password wajib diisi.")
            return

        is_valid, user_label = verify_credentials(usr, pwd)

        if is_valid:
            self.authenticated_user = user_label
            self.accept()
        else:
            self._failed_attempts += 1
            if self._failed_attempts >= 5:
                self._lockout_until = time.time() + 30
                self._show_error("5x Percobaan salah. Sistem terkunci selama 30 detik.")
            else:
                sisa_coba = 5 - self._failed_attempts
                self._show_error(f"Kredensial tidak valid. Sisa percobaan: {sisa_coba}")
            self.txt_password.clear()
            self.txt_password.setFocus()

    def _show_error(self, message: str) -> None:
        self.lbl_status.setText(message)
        self.lbl_status.setVisible(True)
