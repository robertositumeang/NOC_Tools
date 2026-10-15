"""Authentication and access control for NOC Tools.

Packaged applications authenticate operators through the Cloudflare Worker.
Source-mode development retains the local credential-store workflow.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Final

from cloudflare_api import WorkerApiError, operator_login
from PyQt6.QtCore import QObject, QPointF, QRectF, QSize, Qt, QThread, QTimer
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from license_mgr import check_active_license, LicenseActivationDialog
from noc_brand import (
    DARK_THEME,
    LIGHT_THEME,
    NocLogoMark,
    ThemeSelector,
    app_icon,
    paint_network_background,
    set_application_theme,
)
from startup_config import display_settings

_CREDENTIALS_FILE: Final[Path] = (
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    / "NOC Tools"
    / "users.json"
)
_SCRYPT_N: Final[int] = 1 << 14
_SCRYPT_R: Final[int] = 8
_SCRYPT_P: Final[int] = 1
_SCRYPT_DKLEN: Final[int] = 32
_LOGGER = logging.getLogger(__name__)


def _derive_credential_hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )


def _read_credential_records(path: Path | None = None) -> list[dict[str, str]]:
    credential_file = path or _CREDENTIALS_FILE
    store = json.loads(credential_file.read_text(encoding="utf-8"))
    if not isinstance(store, dict) or store.get("version") != 1:
        raise ValueError("Unsupported authentication credential store.")
    users = store.get("users")
    if not isinstance(users, list):
        raise ValueError("Authentication credential store has no user list.")
    for record in users:
        if not isinstance(record, dict) or not all(
            isinstance(record.get(key), str)
            for key in ("username", "display_name", "salt", "password_hash")
        ):
            raise ValueError("Authentication credential store has an invalid user record.")
    return users


def _credential_store_path() -> Path:
    if getattr(sys, "frozen", False):
        portable_store = Path(sys.executable).resolve().with_name("users.json")
        if portable_store.is_file():
            return portable_store
    return _CREDENTIALS_FILE


def verify_credentials(username_input: str, password_input: str) -> tuple[bool, str]:
    """Verify frozen-app credentials online, or source credentials locally.

    Returns (is_valid: bool, display_user: str).
    """
    u_in = (username_input or "").strip()
    p_in = password_input or ""

    if not u_in or not p_in.strip():
        return False, ""

    if getattr(sys, "frozen", False):
        return operator_login(u_in, p_in)

    credential_file = _credential_store_path()
    try:
        records = _read_credential_records(credential_file)
    except FileNotFoundError:
        _LOGGER.error("Authentication credential store is missing: %s", credential_file)
        return False, ""
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        _LOGGER.exception("Unable to read authentication credential store.")
        return False, ""

    record = next((item for item in records if item["username"] == u_in), None)
    if record is None:
        _derive_credential_hash(p_in, bytes(16))
        return False, ""

    try:
        salt = bytes.fromhex(record["salt"])
        expected_hash = bytes.fromhex(record["password_hash"])
        if len(salt) != 16 or len(expected_hash) != _SCRYPT_DKLEN:
            raise ValueError("Authentication credential record has invalid hash data.")
        actual_hash = _derive_credential_hash(p_in, salt)
    except ValueError:
        _LOGGER.exception("Authentication credential record is invalid.")
        return False, ""

    if hmac.compare_digest(actual_hash, expected_hash):
        return True, record["display_name"]
    return False, ""


def _password_toggle_icon(visible: bool) -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#9FB4C4"), 1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    eye = QPainterPath()
    eye.moveTo(2.5, 12)
    eye.cubicTo(5.0, 8.2, 8.1, 6.2, 12, 6.2)
    eye.cubicTo(15.9, 6.2, 19.0, 8.2, 21.5, 12)
    eye.cubicTo(19.0, 15.8, 15.9, 17.8, 12, 17.8)
    eye.cubicTo(8.1, 17.8, 5.0, 15.8, 2.5, 12)
    painter.drawPath(eye)
    painter.drawEllipse(QRectF(9.1, 9.1, 5.8, 5.8))

    if visible:
        painter.drawLine(4, 20, 20, 4)

    painter.end()
    return QIcon(pixmap)



# ── Login UI ───────────────────────────────────────────────────────────────────
_LOGIN_QSS = """
QDialog {
    background: #080D16;
    color: #E6EDF7;
    font-family: 'Segoe UI';
}

QFrame#loginShell {
    background: #081427;
    border: 1px solid #243D5C;
    border-radius: 14px;
}

QFrame#brandPanel {
    background: transparent;
    border: none;
    border-top-left-radius: 13px;
    border-bottom-left-radius: 13px;
}

QFrame#formPanel {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #081427, stop:1 #060F1E
    ); /* #101E30 */
    border: none;
    border-top-right-radius: 13px;
    border-bottom-right-radius: 13px;
}

QLabel#brandMark {
    background: #0D2D52;
    border: 1px solid #1765B1;
    border-radius: 11px;
    color: #43B9FF;
    font-size: 20px;
    font-weight: 700;
    min-width: 42px;
    max-width: 42px;
    min-height: 42px;
    max-height: 42px;
}

QLabel#brandEyebrow, QLabel#formEyebrow {
    color: #36B7FF;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.4px;
}

QLabel#titleLabel {
    color: #F8FAFC;
    font-size: 27px;
    font-weight: 700;
    letter-spacing: 0.2px;
}

QLabel#subtitleLabel {
    color: #91A9C7;
    font-size: 10px;
    letter-spacing: 0.4px;
}

QLabel#brandFootnote {
    color: #829AB8;
    font-size: 9px;
    letter-spacing: 0.5px;
}

QLabel#formTitle {
    color: #F4F7FC;
    font-size: 24px;
    font-weight: 700;
}

QLabel#formHint {
    color: #8FA8C9;
    font-size: 11px;
}

QLabel#showcaseAccent {
    color: #27A8FF;
    font-size: 27px;
    font-weight: 700;
}

QLabel#fieldLabel {
    color: #AFC2DC;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.9px;
}

QLineEdit {
    background: rgba(20, 36, 57, 0.88);
    border: 1px solid #294567;
    border-radius: 9px;
    padding: 11px 13px;
    color: #F1F5F9;
    font-size: 12px;
    selection-background-color: #1678F2;
}

QLineEdit:focus {
    border: 1px solid #3289FF;
    background: #14243A;
}

QLineEdit:disabled {
    background: #121D2C;
    border: 1px solid #26364A;
    color: #64748B;
}

QPushButton#btnLogin {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #126DE8, stop:1 #148BFF
    );
    color: #FFFFFF;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.9px;
    border: none;
    border-radius: 9px;
    padding: 11px 20px;
    min-height: 38px;
}

QPushButton#btnLogin:hover {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #2582FF, stop:1 #40A2FF
    );
    color: #FFFFFF;
}

QPushButton#btnLogin:pressed {
    background: #0D5FCB;
}

QPushButton#btnLogin:disabled {
    background: #1B304B;
    color: #9AB5D6;
    border: 1px solid #2A4260;
}

QPushButton#btnActivateLic {
    background: #A52D47;
    color: #FFFFFF;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.4px;
    border: none;
    border-radius: 8px;
    padding: 7px 14px;
}

QPushButton#btnActivateLic:hover {
    background: #C33C58;
}

QPushButton#btnActivateLic:pressed {
    background: #86253B;
}

QPushButton#btnForgot {
    background: transparent;
    color: #8796A9;
    font-size: 11px;
    border: none;
    text-align: right;
    padding: 4px;
}

QPushButton#btnForgot:hover {
    color: #4EB7FF;
    text-decoration: underline;
}

QPushButton#btnTogglePassword {
    background: #14243A;
    border: 1px solid #294567;
    border-radius: 9px;
    color: #9FB4D3;
    font-size: 16px;
    min-width: 44px;
    padding: 4px;
}

QPushButton#btnTogglePassword:hover {
    color: #4EB7FF;
    border-color: #3289FF;
}

QLabel#errorLabel {
    color: #FF879A;
    font-size: 11px;
    font-weight: 600;
}

QLabel#footerBadge {
    color: #829AB8;
    font-size: 10px;
    letter-spacing: 0.3px;
}

QLabel#adminHint {
    color: #91A9C7;
    font-size: 10px;
}

QLabel#featureTitle {
    color: #D9E8F9;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.3px;
}

QLabel#featureSub {
    color: #829AB8;
    font-size: 8.5px;
}

QLabel#featureSymbol {
    color: #38BDF8;
    background: rgba(14, 165, 233, 0.12);
    border: 1px solid rgba(56, 189, 248, 0.35);
    border-radius: 4px;
    font-size: 10px;
    font-weight: 700;
    min-width: 24px;
    max-width: 24px;
    min-height: 20px;
    max-height: 20px;
}

QLabel#trustBadge {
    color: #829AB8;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 1px;
}
"""

_LOGIN_LIGHT_QSS = """
QDialog {
    background: #E8F0F9;
    color: #15263B;
}

QFrame#loginShell {
    background: #F4F8FD;
    border: 1px solid #D2DFEE;
}

QFrame#formPanel {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #EAF1F9, stop:1 #E2EBF6
    );
}

/* Light mode styling for left brand panel */
QFrame#brandPanel QLabel#brandEyebrow { color: #126FE8; }
QFrame#brandPanel QLabel#titleLabel { color: #15263B; }
QFrame#brandPanel QLabel#subtitleLabel { color: #52677F; }
QFrame#brandPanel QLabel#featureTitle { color: #15263B; }
QFrame#brandPanel QLabel#featureSub { color: #52677F; }
QFrame#brandPanel QLabel#featureSymbol {
    color: #126FE8;
    background: rgba(18, 111, 232, 0.10);
    border: 1px solid rgba(18, 111, 232, 0.30);
}
QFrame#brandPanel QLabel#trustBadge { color: #63788F; }
QFrame#brandPanel QLabel#brandMark {
    background: #EAF1F9;
    border: 1px solid #D2DFEE;
}

QLabel#formTitle { color: #15263B; }
QLabel#formHint, QLabel#adminHint { color: #52677F; }
QLabel#fieldLabel { color: #435B76; }
QLabel#footerBadge, QLabel#brandFootnote { color: #63788F; }
QPushButton#btnForgot { color: #52677F; }
QPushButton#btnForgot:hover { color: #075CC7; }

QLineEdit {
    background: #FFFFFF;
    border: 1px solid #CBD9E8;
    color: #15263B;
    selection-background-color: #126FE8;
}

QLineEdit:focus {
    border: 1px solid #126FE8;
    background: #FFFFFF;
}

QLineEdit:disabled {
    background: #EDF2F8;
    border: 1px solid #D7E1EC;
    color: #8292A4;
}

QPushButton#btnTogglePassword {
    background: #FFFFFF;
    border: 1px solid #CBD9E8;
    color: #52677F;
}

QPushButton#btnTogglePassword:hover {
    color: #075CC7;
    border-color: #126FE8;
}
"""


class _NetworkPanel(QFrame):
    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bounds = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(bounds, 13, 13)
        painter.setClipPath(clip)

        # Detect theme dynamically from dialog
        dialog = self.window()
        is_dark = True
        if hasattr(dialog, "current_theme_name"):
            is_dark = (dialog.current_theme_name == DARK_THEME)

        w = bounds.width()
        h = bounds.height()

        # 1. Base gradient
        background = QLinearGradient(0, 0, w, h)
        if is_dark:
            background.setColorAt(0, QColor("#081427"))
            background.setColorAt(0.50, QColor("#0A1C38"))
            background.setColorAt(1, QColor("#050C18"))
        else:
            background.setColorAt(0, QColor("#F4F8FD"))
            background.setColorAt(0.50, QColor("#EAF1F9"))
            background.setColorAt(1, QColor("#DFEBF8"))
        painter.fillRect(bounds, background)

        # 2. Tech perspective grid on bottom-half
        grid_pen = QPen(
            QColor(56, 189, 248, 22 if is_dark else 15),
            1.0,
            Qt.PenStyle.SolidLine
        )
        painter.setPen(grid_pen)
        # Horizontal perspective lines
        for y_factor in (0.62, 0.70, 0.79, 0.89, 0.98):
            y = h * y_factor
            painter.drawLine(QPointF(0, y), QPointF(w, y))
        # Vanishing vertical rays converging towards top center-left
        vanishing_pt = QPointF(w * 0.40, h * 0.45)
        for x_factor in (0.0, 0.15, 0.30, 0.50, 0.70, 0.85, 1.0):
            painter.drawLine(vanishing_pt, QPointF(w * x_factor, h))

        # 3. Dynamic radial glow accents
        radial_glow = QRadialGradient(QPointF(w * 0.75, h * 0.40), w * 0.60)
        if is_dark:
            radial_glow.setColorAt(0.0, QColor(14, 165, 233, 40))
            radial_glow.setColorAt(0.5, QColor(2, 132, 199, 15))
            radial_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        else:
            radial_glow.setColorAt(0.0, QColor(14, 165, 233, 30))
            radial_glow.setColorAt(0.5, QColor(2, 132, 199, 10))
            radial_glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(bounds, radial_glow)

        # 4. Sleek futuristic concentric telemetry rings
        ring_center = QPointF(w * 0.82, h * 0.78)
        ring_pen = QPen(QColor(56, 189, 248, 55 if is_dark else 40), 1.2)
        ring_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for r in (50, 100, 160, 230):
            painter.drawEllipse(ring_center, r, r)

        # 5. Connected constellation data points with pulsing glowing rings
        node_pen = QPen(QColor(56, 189, 248, 120 if is_dark else 90), 1.0)
        painter.setPen(node_pen)
        pts = [
            QPointF(w * 0.12, h * 0.76),
            QPointF(w * 0.28, h * 0.65),
            QPointF(w * 0.48, h * 0.72),
            QPointF(w * 0.68, h * 0.60),
            QPointF(w * 0.86, h * 0.68),
        ]
        for i in range(len(pts) - 1):
            painter.drawLine(pts[i], pts[i + 1])

        # Pulse nodes
        for pt in pts:
            # Outer ring
            painter.setPen(QPen(QColor(56, 189, 248, 70 if is_dark else 50), 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(pt, 5.0, 5.0)
            # Center core
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(56, 189, 248, 220 if is_dark else 180))
            painter.drawEllipse(pt, 2.5, 2.5)


class _LoginSpinner(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(18, 18)
        self.setAccessibleName("Memverifikasi kredensial")
        self._timer = QTimer(self)
        self._timer.setInterval(45)
        self._timer.timeout.connect(self._advance)
        self.hide()

    @property
    def angle(self) -> int:
        return self._angle

    def start(self) -> None:
        self._angle = 0
        self.show()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _advance(self) -> None:
        self._angle = (self._angle + 24) % 360
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#4FD1C1"), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(
            QRectF(self.rect()).adjusted(2, 2, -2, -2),
            self._angle * 16,
            255 * 16,
        )


class _CredentialCheckThread(QThread):
    def __init__(
        self,
        username: str,
        password: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._username = username
        self._password = password
        self.result: tuple[bool, str] = (False, "")
        self.error_message = ""

    def run(self) -> None:
        try:
            self.result = verify_credentials(self._username, self._password)
        except WorkerApiError as error:
            self.error_message = str(error)


class LoginDialog(QDialog):
    """Secure, Anti-Slop Production-Grade Login Window with Pre-Login License Gate."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("NOC Security Access Control")
        application = QApplication.instance()
        theme_name = (
            application.property("nocTheme") if application is not None else None
        ) or DARK_THEME
        self.current_theme_name = theme_name
        self.setWindowIcon(app_icon(theme_name))
        self.setFixedSize(960, 590)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet(
            _LOGIN_QSS
            + (_LOGIN_LIGHT_QSS if theme_name == LIGHT_THEME else "")
        )

        self.authenticated_user: str = ""
        self._failed_attempts: int = 0
        self._lockout_until: float = 0.0

        # License state attributes
        self._is_lic_valid: bool = False
        self._lic_days_left: int = 0
        self._lic_msg: str = ""
        self._lic_exp_date: str = ""
        self._auth_thread: _CredentialCheckThread | None = None

        self._build_ui()
        self._refresh_license_status()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        shell = QFrame()
        shell.setObjectName("loginShell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        brand_panel = _NetworkPanel()
        brand_panel.setObjectName("brandPanel")
        brand_panel.setMinimumWidth(480)
        brand_layout = QVBoxLayout(brand_panel)
        brand_layout.setContentsMargins(32, 28, 30, 23)
        brand_layout.setSpacing(0)

        brand_header = QHBoxLayout()
        brand_header.setSpacing(11)
        brand_mark = NocLogoMark(42)
        brand_mark.setObjectName("brandMark")
        brand_header.addWidget(brand_mark)

        brand_details = QVBoxLayout()
        brand_details.setSpacing(4)
        brand_title = QLabel("NOC Tools")
        brand_title.setObjectName("titleLabel")
        brand_title.setStyleSheet("font-size: 16px;")
        brand_details.addWidget(brand_title)

        brand_subtitle = QLabel("PT. KEREAKTIF INDONESIA")
        brand_subtitle.setObjectName("subtitleLabel")
        brand_details.addWidget(brand_subtitle)
        brand_header.addLayout(brand_details)
        brand_header.addStretch()
        brand_layout.addLayout(brand_header)
        brand_layout.addStretch(2)

        showcase_eyebrow = QLabel("NOC OPERATIONS")
        showcase_eyebrow.setObjectName("brandEyebrow")
        brand_layout.addWidget(showcase_eyebrow)
        brand_layout.addSpacing(10)

        showcase_title = QLabel("Additional Tools")
        showcase_title.setObjectName("titleLabel")
        showcase_title.setStyleSheet("font-size: 26px;")
        brand_layout.addWidget(showcase_title)

        showcase_accent = QLabel("for NOC Operations")
        showcase_accent.setObjectName("showcaseAccent")
        brand_layout.addWidget(showcase_accent)
        brand_layout.addSpacing(8)

        showcase_copy = QLabel(
            "Integrated workspace and diagnostic suite for NOC field & central teams."
        )
        showcase_copy.setObjectName("formHint")
        showcase_copy.setWordWrap(True)
        showcase_copy.setMaximumWidth(400)
        brand_layout.addWidget(showcase_copy)
        brand_layout.addSpacing(16)

        # ── 5 Active Features (excluding VPN Manager) ──
        feature_grid = QGridLayout()
        feature_grid.setHorizontalSpacing(16)
        feature_grid.setVerticalSpacing(10)

        modules = [
            ("01", "DASHBOARD", "Trouble Ticket Monitor"),
            ("02", "AUDIT", "Ticket Checker Gap"),
            ("03", "ANALYSIS", "Check Massive Alarms"),
            ("04", "CAPTURE MODEM", "VSAT Modem Diagnostics"),
            ("05", "CAPTURE", "CCTV Extractor"),
        ]

        for i, (symbol, title, subtitle) in enumerate(modules):
            row = i // 2
            col = i % 2
            item_box = QHBoxLayout()
            item_box.setSpacing(8)

            sym_lbl = QLabel(symbol)
            sym_lbl.setObjectName("featureSymbol")
            sym_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            item_box.addWidget(sym_lbl)

            text_col = QVBoxLayout()
            text_col.setSpacing(1)
            t_lbl = QLabel(title)
            t_lbl.setObjectName("featureTitle")
            sub_lbl = QLabel(subtitle)
            sub_lbl.setObjectName("featureSub")
            text_col.addWidget(t_lbl)
            text_col.addWidget(sub_lbl)
            item_box.addLayout(text_col)

            feature_grid.addLayout(item_box, row, col)

        brand_layout.addLayout(feature_grid)
        brand_layout.addStretch(1)

        brand_footer = QLabel("FAST   ·   RELIABLE   ·   SECURE")
        brand_footer.setObjectName("trustBadge")
        brand_layout.addWidget(brand_footer)
        shell_layout.addWidget(brand_panel, 12)

        form_panel = QFrame()
        form_panel.setObjectName("formPanel")
        form_panel.setMaximumWidth(456)
        card_layout = QVBoxLayout(form_panel)
        card_layout.setContentsMargins(34, 38, 34, 25)
        card_layout.setSpacing(9)

        theme_row = QHBoxLayout()
        theme_row.addStretch(1)
        self.theme_selector = ThemeSelector(self.current_theme_name)
        self.theme_selector.themeChanged.connect(self._apply_theme)
        theme_row.addWidget(self.theme_selector)
        card_layout.addLayout(theme_row)

        card_layout.addStretch(2)
        form_title = QLabel("Welcome Back")
        form_title.setObjectName("formTitle")
        card_layout.addWidget(form_title)

        form_hint = QLabel("Sign in to access NOC Tools.")
        form_hint.setObjectName("formHint")
        card_layout.addWidget(form_hint)
        card_layout.addSpacing(12)

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

        self.btn_activate_lic = QPushButton("🔑 Activate")
        self.btn_activate_lic.setObjectName("btnActivateLic")
        self.btn_activate_lic.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_activate_lic.clicked.connect(self._handle_activate_license)
        lic_card_layout.addWidget(self.btn_activate_lic)

        card_layout.addWidget(self.lic_card)
        card_layout.addSpacing(2)

        # ── Username Field ─────────────────────────────────────────────────
        lbl_user = QLabel("USERNAME")
        lbl_user.setObjectName("fieldLabel")
        card_layout.addWidget(lbl_user)

        self.txt_username = QLineEdit()
        self.txt_username.setPlaceholderText("Enter username...")
        self.txt_username.returnPressed.connect(self._focus_password)
        card_layout.addWidget(self.txt_username)
        card_layout.addSpacing(1)

        # ── Password Field ─────────────────────────────────────────────────
        lbl_pass = QLabel("PASSWORD")
        lbl_pass.setObjectName("fieldLabel")
        card_layout.addWidget(lbl_pass)

        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("Password")
        self.txt_password.returnPressed.connect(self._handle_login)
        password_row = QHBoxLayout()
        password_row.setSpacing(6)
        password_row.addWidget(self.txt_password, stretch=1)

        self.btn_toggle_password = QPushButton()
        self.btn_toggle_password.setObjectName("btnTogglePassword")
        self.btn_toggle_password.setIcon(_password_toggle_icon(visible=False))
        self.btn_toggle_password.setIconSize(QSize(20, 20))
        self.btn_toggle_password.setCheckable(True)
        self.btn_toggle_password.setAccessibleName("Toggle password visibility")
        self.btn_toggle_password.setToolTip("Toggle password visibility")
        self.btn_toggle_password.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_password.toggled.connect(self._toggle_password_visibility)
        password_row.addWidget(self.btn_toggle_password)
        card_layout.addLayout(password_row)

        # ── Forgot Password Action ─────────────────────────────────────────
        row_forgot = QHBoxLayout()
        row_forgot.addStretch()
        self.btn_forgot = QPushButton("Forgot Password?")
        self.btn_forgot.setObjectName("btnForgot")
        self.btn_forgot.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_forgot.clicked.connect(self._handle_forgot_password)
        row_forgot.addWidget(self.btn_forgot)
        card_layout.addLayout(row_forgot)

        # ── Status / Error Banner ──────────────────────────────────────────
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("errorLabel")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setVisible(False)
        card_layout.addWidget(self.lbl_status)

        busy_row = QHBoxLayout()
        busy_row.setSpacing(8)
        busy_row.addStretch()
        self.login_spinner = _LoginSpinner(self)
        busy_row.addWidget(self.login_spinner)
        self.lbl_loading = QLabel("Verifying credentials...")
        self.lbl_loading.setObjectName("adminHint")
        busy_row.addWidget(self.lbl_loading)
        busy_row.addStretch()
        self.lbl_loading.hide()
        card_layout.addLayout(busy_row)

        # ── Login Button ───────────────────────────────────────────────────
        self.btn_login = QPushButton("SIGN IN TO SYSTEM  ➔")
        self.btn_login.setObjectName("btnLogin")
        self.btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_login.clicked.connect(self._handle_login)
        card_layout.addWidget(self.btn_login)

        card_layout.addStretch(2)

        # ── Footer Security Badge ──────────────────────────────────────────
        footer = QLabel("Admin : PT. KEREAKTIF INDONESIA")
        footer.setObjectName("footerBadge")
        footer.setAlignment(Qt.AlignmentFlag.AlignRight)
        card_layout.addWidget(footer)

        operations_tagline = QLabel("OPERATIONS  /  MONITORING  /  RESPONSE")
        operations_tagline.setObjectName("brandFootnote")
        operations_tagline.setAlignment(Qt.AlignmentFlag.AlignRight)
        card_layout.addWidget(operations_tagline)

        shell_layout.addWidget(form_panel, 9)
        layout.addWidget(shell)

    def _apply_theme(self, theme_name: str) -> None:
        self.current_theme_name = theme_name
        if application := QApplication.instance():
            set_application_theme(theme_name, application)
        self.setWindowIcon(app_icon(theme_name))
        self.setStyleSheet(
            _LOGIN_QSS
            + (_LOGIN_LIGHT_QSS if theme_name == LIGHT_THEME else "")
        )
        self.theme_selector.set_theme(theme_name)
        display_settings().setValue("appearance/theme", theme_name)

    def _refresh_license_status(self) -> None:
        """Evaluate license state and lock/unlock login controls accordingly."""
        is_valid, msg, days_left, exp_date = check_active_license()
        self._is_lic_valid = is_valid
        self._lic_days_left = days_left
        self._lic_msg = msg
        self._lic_exp_date = exp_date

        if self._is_lic_valid:
            self.lic_card.setVisible(False)
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
            self.btn_login.setText("MASUK KE SISTEM")
            self.lbl_status.setVisible(False)
        else:
            self.lic_card.setVisible(True)
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

    def _toggle_password_visibility(self, visible: bool) -> None:
        cursor_position = self.txt_password.cursorPosition()
        echo_mode = (
            QLineEdit.EchoMode.Normal
            if visible
            else QLineEdit.EchoMode.Password
        )
        self.txt_password.setEchoMode(echo_mode)
        self.txt_password.setCursorPosition(cursor_position)
        self.btn_toggle_password.setIcon(_password_toggle_icon(visible=visible))
        action = "Sembunyikan" if visible else "Tampilkan"
        self.btn_toggle_password.setAccessibleName(f"{action} kata sandi")
        self.btn_toggle_password.setToolTip(f"{action} kata sandi")

    def _handle_forgot_password(self) -> None:
        """Requirement: Jika lupa password HANYA notif contact administrator."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Bantuan Akses Akun")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("<b>Akses Dibatasi</b>")
        msg.setInformativeText(
            "Untuk alasan keamanan aplikasi dan kebahagiaan developer reset "
            "kata sandi mandiri tidak diperbolehkan.\n\n"
            'Silahkan hubungi Developer tools ini, "BANG BERT" untuk '
            "verifikasi identitas anda."
        )
        msg.exec()

    def _handle_login(self) -> None:
        if not self._is_lic_valid:
            self._show_error("Lisensi tidak aktif atau kedaluwarsa. Silakan aktivasi dahulu.")
            return
        if self._auth_thread is not None:
            return

        now = time.time()
        if now < self._lockout_until:
            sisa = int(self._lockout_until - now)
            self._show_error(f"Terlalu banyak percobaan gagal. Silakan tunggu {sisa} detik.")
            return

        usr = self.txt_username.text().strip()
        pwd = self.txt_password.text()

        if not usr or not pwd:
            self._show_error("Username dan Password wajib diisi.")
            return

        self.lbl_status.setVisible(False)
        self._set_login_busy(True)
        thread = _CredentialCheckThread(usr, pwd, QApplication.instance())
        self._auth_thread = thread
        thread.finished.connect(self._complete_login)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _set_login_busy(self, busy: bool) -> None:
        if busy:
            self.login_spinner.start()
            self.lbl_loading.show()
            self.btn_login.setText("MEMVERIFIKASI...")
        else:
            self.login_spinner.stop()
            self.lbl_loading.hide()
            self.btn_login.setText("MASUK KE SISTEM  ➔")

        self.txt_username.setEnabled(not busy and self._is_lic_valid)
        self.txt_password.setEnabled(not busy and self._is_lic_valid)
        self.btn_toggle_password.setEnabled(not busy and self._is_lic_valid)
        self.btn_forgot.setEnabled(not busy)
        self.btn_login.setEnabled(not busy and self._is_lic_valid)

    def _complete_login(self) -> None:
        thread = self._auth_thread
        if thread is None:
            return
        is_valid, user_label = thread.result
        error_message = thread.error_message
        self._auth_thread = None
        self._set_login_busy(False)
        if is_valid:
            self.authenticated_user = user_label
            self.accept()
        elif error_message:
            self._show_error(error_message)
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
