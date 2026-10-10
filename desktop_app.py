from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Callable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from PyQt6.QtCore import (
    QDate,
    QDateTime,
    QEvent,
    QObject,
    QRect,
    QSettings,
    Qt,
    QTime,
    QThread,
    pyqtSignal,
    QTimer,
    QUrl,
)
from PyQt6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from noc_brand import (
    APP_NAME,
    APP_VERSION,
    DARK_THEME,
    NocLogoMark,
    ThemeSelector,
    THEMES,
    apply_standard_window_chrome,
    app_icon,
    set_application_theme,
    system_theme_name,
    theme_stylesheet,
)

from startup_config import (
    DEFAULT_SCALE_PERCENT,
    SCALE_OPTIONS,
    display_settings as _display_settings,
    qt_scale_factor as _qt_scale_factor,
    saved_scale_percent as _saved_scale_percent,
    system_dpi as _system_dpi,
)

from alarm_analysis import (
    build_site_index,
    detect_alarm_vendor,
    normalize_alarms,
    read_table,
    summarize_providers,
)
from updater import (
    CheckUpdateWorker,
    UpdateDialog,
    configure_github_repo_dialog,
    get_github_repo,
)


DEFAULT_MASTER_FILENAME = "Site Management -  20260927_160847.xlsx"
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
    MASTER_SOURCE_DIR = RESOURCE_DIR / "site_management"
else:
    BASE_DIR = Path(__file__).resolve().parent
    RESOURCE_DIR = BASE_DIR
    MASTER_SOURCE_DIR = BASE_DIR

APP_ICON_PATH = RESOURCE_DIR / "app_icon.ico"
# Cari folder cctv_report: di samping noc_massive/ (dev) atau di MEIPASS (frozen)
_cctv_candidates = [
    RESOURCE_DIR / "cctv_report",          # frozen: _MEIPASS/cctv_report
    BASE_DIR.parent / "cctv_report",        # dev: ../cctv_report/ (sibling)
    RESOURCE_DIR / "CCTV_Report",           # legacy path
    BASE_DIR / "CCTV_Report",              # legacy path (same dir)
]
CCTV_MODULE_DIR = next((p for p in _cctv_candidates if p.is_dir()), None)
if CCTV_MODULE_DIR is None:
    raise FileNotFoundError(
        "CCTV Report module tidak ditemukan. Pastikan folder cctv_report/ ada di project."
    )
if str(CCTV_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(CCTV_MODULE_DIR))

from cctv_report_app import MainWindow as CCTVReportMainWindow

matching_masters = sorted(MASTER_SOURCE_DIR.glob("Site Management*.xlsx"))
DEFAULT_MASTER_PATH = matching_masters[-1] if matching_masters else MASTER_SOURCE_DIR / DEFAULT_MASTER_FILENAME

WINDOW_RESOLUTIONS = {
    "1280x720": (1280, 720),
    "1366x768": (1366, 768),
    "1600x900": (1600, 900),
    "1920x1080": (1920, 1080),
    "2560x1440": (2560, 1440),
}
DEFAULT_RESOLUTION = "1920x1080"


def _saved_resolution(settings: QSettings | None = None) -> str:
    settings = settings or _display_settings()
    resolution = str(
        settings.value("display/resolution", DEFAULT_RESOLUTION)
    )
    return resolution if resolution in WINDOW_RESOLUTIONS else DEFAULT_RESOLUTION


def _window_geometry_for_resolution(
    resolution: tuple[int, int],
    scale_percent: int,
    available_geometry: QRect,
) -> QRect:
    if scale_percent <= 0:
        raise ValueError("Scale percentage must be positive.")
    requested_width, requested_height = resolution
    width = min(
        round(requested_width * 100 / scale_percent),
        available_geometry.width(),
    )
    height = min(
        round(requested_height * 100 / scale_percent),
        available_geometry.height(),
    )
    x = available_geometry.x() + (available_geometry.width() - width) // 2
    y = available_geometry.y() + (available_geometry.height() - height) // 2
    return QRect(x, y, width, height)


def _apply_window_resolution(
    window: QMainWindow,
    resolution: str,
    scale_percent: int,
) -> None:
    application = QApplication.instance()
    screen = window.screen() if application is not None else None
    if screen is None and application is not None:
        screen = application.primaryScreen()
    if screen is None:
        return
    window.setGeometry(
        _window_geometry_for_resolution(
            WINDOW_RESOLUTIONS[resolution],
            scale_percent,
            screen.availableGeometry(),
        )
    )


class _LauncherReturnFilter(QObject):
    def __init__(
        self,
        on_window_closed: Callable[[QMainWindow], None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._active_window: QMainWindow | None = None
        self._on_window_closed = on_window_closed
        self._retired_windows: list[QMainWindow] = []
        self._retirement_timer = QTimer(self)
        self._retirement_timer.setInterval(50)
        self._retirement_timer.timeout.connect(self._reap_retired_windows)

    def set_active_window(self, window: QMainWindow) -> None:
        self._active_window = window
        window.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            watched is self._active_window
            and event.type() == QEvent.Type.Close
        ):
            closing_window = self._active_window
            self._active_window = None
            QTimer.singleShot(
                0,
                lambda: self._dispatch_window_closed(closing_window),
            )
        return False

    def _dispatch_window_closed(self, window: QMainWindow | None) -> None:
        if window is None:
            return
        self._retired_windows.append(window)
        if not self._retirement_timer.isActive():
            self._retirement_timer.start()
        self._on_window_closed(window)

    def _reap_retired_windows(self) -> None:
        remaining: list[QMainWindow] = []
        for window in self._retired_windows:
            workers = [
                getattr(window, name, None)
                for name in ("worker", "import_worker", "export_worker")
            ]
            running_threads = [
                thread
                for thread in (*workers, *window.findChildren(QThread))
                if isinstance(thread, QThread)
                if thread.isRunning()
            ]
            if running_threads:
                remaining.append(window)
                continue

            if getattr(window, "_close_pending", False):
                setattr(window, "_close_pending", False)
                window.close()
            window.deleteLater()

        self._retired_windows = remaining
        if not remaining:
            self._retirement_timer.stop()


DOWN_ALARM_HINTS = (
    "disconnect", "out of service", "link", "outage", "power cut",
    "power-off", "power off", "unavailable", "broken", "fault", "down",
)

PREFERRED_DOWN_ALARMS = {
    # ZTE
    "the link between the server and the me is broken",
    # Fiberhome
    "cell out of service",
    "enb out of service",
    "ne disconnected",
    # Huawei
    "enodeb unavailable",
    "cell unavailable",
    "sctp link congestion",
}

FIBERHOME_PREFERRED_ALARM_HINTS = ("s1 link",)


def _preferred_alarm_names(alarms: list[dict]) -> set[str]:
    alarm_names = {alarm["Alarm Name"] for alarm in alarms}
    preferred = {
        name
        for name in alarm_names
        if name.casefold().strip() in PREFERRED_DOWN_ALARMS
    }
    fiberhome_s1_link_names = {
        alarm["Alarm Name"]
        for alarm in alarms
        if (alarm.get("Vendor") or "").strip().casefold() == "fiberhome"
        and any(
            hint in alarm["Alarm Name"].casefold()
            for hint in FIBERHOME_PREFERRED_ALARM_HINTS
        )
    }
    if not preferred:
        preferred = {
            name
            for name in alarm_names
            if any(hint in name.casefold() for hint in DOWN_ALARM_HINTS)
        }
    preferred.update(fiberhome_s1_link_names)
    return preferred if preferred else alarm_names


NORMALIZED_COLUMNS = [
    "Vendor", "Site ID", "Site Name", "VSAT Provider", "Spotbeam", "Status BAPL",
    "Region", "Paket", "Area", "Alarm Name", "Alarm Type", "Severity",
    "Occurrence Time", "Clear Time", "Duration", "Alarm State", "NE ID", "Alarm ID",
    "Vendor Transmisi",
]

SUMMARY_REPORT_COLUMNS = [
    "Range Start", "Range End", "VSAT Provider", "Spotbeam", "Current Down Sites",
    "Peak Simultaneous Sites", "Peak Time", "Massive Down", "Sites at Peak",
]


SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


THEMES_QSS = {
    "Obsidian Glass (Dark)": {
        "app_bg": "#0a0e17",
        "card_bg": "#111827",
        "card_alt": "#162032",
        "border": "#1f2d42",
        "text": "#f8fafc",
        "muted": "#94a3b8",
        "accent": "#06b6d4",
        "accent_hover": "#0891b2",
        "signal": "#f59e0b",
        "alert": "#f43f5e",
        "table_row_alt": "#141d2e",
        "massive_bg": "#3b1118",
        "massive_text": "#fda4af",
        "qss": """
            QMainWindow, QDialog, QWidget#centralWidget { background-color: #0a0e17; color: #f8fafc; font-family: 'Segoe UI', sans-serif; }
            QFrame#card { background-color: #111827; border: 1px solid #1f2d42; border-radius: 10px; }
            QFrame#headerCard { background-color: #0d131f; border-bottom: 1px solid #1f2d42; padding: 6px 12px; }
            QFrame#footerCard { background-color: #0d131f; border-top: 1px solid #1f2d42; padding: 3px 10px; }
            QLabel { color: #f8fafc; font-size: 12px; }
            QLabel#headerTitle { font-size: 16px; font-weight: bold; color: #f8fafc; }
            QLabel#themeTag { font-size: 11px; font-weight: bold; color: #94a3b8; }
            QLabel#filterTag { font-size: 11px; font-weight: bold; color: #94a3b8; }
            QLabel#metricName { font-size: 10px; font-weight: bold; color: #94a3b8; text-transform: uppercase; }
            QLabel#metricValue { font-size: 24px; font-weight: bold; }
            QLabel#metricSub { font-size: 10px; color: #64748b; }
            QLabel#sectionTitle { font-size: 11px; font-weight: bold; color: #06b6d4; text-transform: uppercase; }
            QLabel#footerText { font-size: 11px; color: #94a3b8; }
            QLineEdit, QSpinBox, QDateEdit, QTimeEdit, QComboBox {
                background-color: #0b111c; color: #f8fafc; border: 1px solid #1f2d42;
                border-radius: 6px; padding: 5px 8px; font-size: 12px; selection-background-color: #06b6d4;
                selection-color: #ffffff;
            }
            QLineEdit:disabled { background-color: #080d14; color: #475569; }
            QComboBox::drop-down { border: none; width: 22px; }
            QComboBox QAbstractItemView {
                background-color: #111827; color: #f8fafc; border: 1px solid #1f2d42;
                selection-background-color: #06b6d4; selection-color: #ffffff; padding: 4px;
            }
            QDateEdit, QTimeEdit {
                padding-right: 2px;
            }
            QDateEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid #1f2d42;
            }
            QPushButton {
                background-color: #162032; color: #f8fafc; border: 1px solid #1f2d42;
                border-radius: 6px; padding: 6px 12px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background-color: #1e2c44; border-color: #06b6d4; }
            QPushButton#accentBtn {
                background-color: #06b6d4; color: #ffffff; border: none; border-radius: 6px; padding: 7px 14px;
            }
            QPushButton#accentBtn:hover { background-color: #0891b2; }
            QPushButton#pillBtn {
                background-color: #162032; color: #f8fafc; border: 1px solid #1f2d42;
                border-radius: 6px; padding: 5px 10px; font-size: 11px;
            }
            QPushButton#pillBtn:hover { border-color: #06b6d4; }
            QTabWidget::pane { border: 1px solid #1f2d42; background: #111827; border-radius: 8px; }
            QTabBar::tab {
                background: #162032; color: #94a3b8; padding: 8px 18px; margin-right: 3px;
                border-top-left-radius: 6px; border-top-right-radius: 6px; font-weight: bold; font-size: 12px;
            }
            QTabBar::tab:selected { background: #06b6d4; color: #ffffff; }
            QTableWidget {
                background-color: #111827; alternate-background-color: #141d2e; color: #f8fafc;
                gridline-color: #1a2538; border: none; border-radius: 6px; font-size: 12px;
                selection-background-color: #0e4554; selection-color: #ecfeff;
            }
            QHeaderView::section {
                background-color: #1a2538; color: #94a3b8; font-weight: bold;
                border: 1px solid #1f2d42; padding: 6px 8px; font-size: 11px;
            }
            QScrollBar:vertical {
                background: #111827; width: 10px; border-radius: 5px; margin: 0;
            }
            QScrollBar::handle:vertical { background: #1f2d42; border-radius: 5px; min-height: 20px; }
            QScrollBar::handle:vertical:hover { background: #06b6d4; }
            QScrollBar:horizontal {
                background: #111827; height: 10px; border-radius: 5px; margin: 0;
            }
            QScrollBar::handle:horizontal { background: #1f2d42; border-radius: 5px; min-width: 20px; }
            QScrollBar::handle:horizontal:hover { background: #06b6d4; }
            QRadioButton, QCheckBox { color: #f8fafc; font-size: 12px; spacing: 6px; }
            QMenu { background-color: #111827; color: #f8fafc; border: 1px solid #1f2d42; border-radius: 6px; padding: 4px; }
            QMenu::item:selected { background-color: #06b6d4; color: #ffffff; border-radius: 4px; }
            QProgressBar {
                background-color: #0b111c; border: 1px solid #1f2d42; border-radius: 3px; height: 6px; text-align: center;
            }
            QProgressBar::chunk { background-color: #06b6d4; border-radius: 2px; }
            QFrame#progressDeck {
                background-color: #141d2e; border: 1px solid #1f2d42; border-radius: 8px; padding: 6px 10px;
            }
            QLabel#footerSpinner { color: #06b6d4; font-size: 13px; font-weight: bold; }
            QLabel#statusTag { color: #06b6d4; font-weight: bold; font-size: 11px; }
            QToolTip {
                background-color: #1e293b; color: #f8fafc; border: 1px solid #06b6d4;
                border-radius: 5px; padding: 6px 10px; font-size: 11px;
            }
            QFrame#hintCard {
                background-color: rgba(6, 182, 212, 0.08); border: 1px solid rgba(6, 182, 212, 0.28);
                border-radius: 6px;
            }
            QLabel#hintText { color: #38bdf8; font-size: 11px; }
        """
    },
    "Soft Slate (Light)": {
        "app_bg": "#eef2f6",
        "card_bg": "#ffffff",
        "card_alt": "#f8fafc",
        "border": "#cbd5e1",
        "text": "#0f172a",
        "muted": "#475569",
        "accent": "#0284c7",
        "accent_hover": "#0369a1",
        "signal": "#d97706",
        "alert": "#dc2626",
        "table_row_alt": "#f8fafc",
        "massive_bg": "#fee2e2",
        "massive_text": "#991b1b",
        "qss": """
            QMainWindow, QDialog, QWidget#centralWidget { background-color: #eef2f6; color: #0f172a; font-family: 'Segoe UI', sans-serif; }
            QFrame#card { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 10px; }
            QFrame#headerCard { background-color: #e2e8f0; border-bottom: 1px solid #cbd5e1; padding: 6px 12px; }
            QFrame#footerCard { background-color: #e2e8f0; border-top: 1px solid #cbd5e1; padding: 3px 10px; }
            QLabel { color: #0f172a; font-size: 12px; }
            QLabel#headerTitle { font-size: 16px; font-weight: bold; color: #0f172a; }
            QLabel#themeTag { font-size: 11px; font-weight: bold; color: #475569; }
            QLabel#filterTag { font-size: 11px; font-weight: bold; color: #475569; }
            QLabel#metricName { font-size: 10px; font-weight: bold; color: #475569; text-transform: uppercase; }
            QLabel#metricValue { font-size: 24px; font-weight: bold; }
            QLabel#metricSub { font-size: 10px; color: #64748b; }
            QLabel#sectionTitle { font-size: 11px; font-weight: bold; color: #0284c7; text-transform: uppercase; }
            QLabel#footerText { font-size: 11px; color: #334155; }
            QLineEdit, QSpinBox, QDateEdit, QTimeEdit, QComboBox {
                background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1;
                border-radius: 6px; padding: 5px 8px; font-size: 12px; selection-background-color: #0284c7;
                selection-color: #ffffff;
            }
            QLineEdit:disabled { background-color: #f1f5f9; color: #64748b; }
            QComboBox::drop-down { border: none; width: 22px; }
            QComboBox QAbstractItemView {
                background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1;
                selection-background-color: #0284c7; selection-color: #ffffff; padding: 4px;
            }
            QDateEdit, QTimeEdit {
                padding-right: 2px;
            }
            QDateEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid #cbd5e1;
            }
            QPushButton {
                background-color: #f8fafc; color: #0f172a; border: 1px solid #cbd5e1;
                border-radius: 6px; padding: 6px 12px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background-color: #e2e8f0; border-color: #0284c7; }
            QPushButton#accentBtn {
                background-color: #0284c7; color: #ffffff; border: none; border-radius: 6px; padding: 7px 14px;
            }
            QPushButton#accentBtn:hover { background-color: #0369a1; }
            QPushButton#pillBtn {
                background-color: #f8fafc; color: #0f172a; border: 1px solid #cbd5e1;
                border-radius: 6px; padding: 5px 10px; font-size: 11px;
            }
            QPushButton#pillBtn:hover { border-color: #0284c7; background-color: #e2e8f0; }
            QTabWidget::pane { border: 1px solid #cbd5e1; background: #ffffff; border-radius: 8px; }
            QTabBar::tab {
                background: #e2e8f0; color: #475569; padding: 8px 18px; margin-right: 3px;
                border-top-left-radius: 6px; border-top-right-radius: 6px; font-weight: bold; font-size: 12px;
            }
            QTabBar::tab:selected { background: #0284c7; color: #ffffff; }
            QTableWidget {
                background-color: #ffffff; alternate-background-color: #f8fafc; color: #0f172a;
                gridline-color: #e2e8f0; border: none; border-radius: 6px; font-size: 12px;
                selection-background-color: #e0f2fe; selection-color: #0369a1;
            }
            QHeaderView::section {
                background-color: #e2e8f0; color: #1e293b; font-weight: bold;
                border: 1px solid #cbd5e1; padding: 6px 8px; font-size: 11px;
            }
            QScrollBar:vertical {
                background: #eef2f6; width: 10px; border-radius: 5px; margin: 0;
            }
            QScrollBar::handle:vertical { background: #cbd5e1; border-radius: 5px; min-height: 20px; }
            QScrollBar::handle:vertical:hover { background: #0284c7; }
            QScrollBar:horizontal {
                background: #eef2f6; height: 10px; border-radius: 5px; margin: 0;
            }
            QScrollBar::handle:horizontal { background: #cbd5e1; border-radius: 5px; min-width: 20px; }
            QScrollBar::handle:horizontal:hover { background: #0284c7; }
            QRadioButton, QCheckBox { color: #0f172a; font-size: 12px; spacing: 6px; }
            QMenu { background-color: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 6px; padding: 4px; }
            QMenu::item:selected { background-color: #0284c7; color: #ffffff; border-radius: 4px; }
            QProgressBar {
                background-color: #e2e8f0; border: 1px solid #cbd5e1; border-radius: 3px; height: 6px; text-align: center;
            }
            QProgressBar::chunk { background-color: #0284c7; border-radius: 2px; }
            QFrame#progressDeck {
                background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 6px 10px;
            }
            QLabel#footerSpinner { color: #0284c7; font-size: 13px; font-weight: bold; }
            QLabel#statusTag { color: #0284c7; font-weight: bold; font-size: 11px; }
            QToolTip {
                background-color: #ffffff; color: #0f172a; border: 1px solid #0284c7;
                border-radius: 5px; padding: 6px 10px; font-size: 11px;
            }
            QFrame#hintCard {
                background-color: #f0f9ff; border: 1px solid #bae6fd;
                border-radius: 6px;
            }
            QLabel#hintText { color: #0284c7; font-size: 11px; }
        """
    },
}


THEMES_QSS = {
    theme_name: {
        **theme,
        "qss": theme_stylesheet(theme_name),
    }
    for theme_name, theme in THEMES.items()
}


def _format_datetime(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def _alarm_overlaps_range(alarm: dict, range_start: datetime, range_end: datetime) -> bool:
    occurrence = alarm.get("Occurrence Time")
    if occurrence is None:
        return False
    clear_time = alarm.get("Clear Time")
    return occurrence < range_end and (clear_time is None or clear_time > range_start)


def _executive_summary_text(alarms: list[dict], site_rows: list[dict], summaries: list[dict]) -> str:
    sites_by_id: dict[str, dict] = {}
    for site in site_rows:
        site_id = str(site.get("Site ID") or "").strip()
        if site_id:
            sites_by_id.setdefault(site_id, site)

    impacted_site_ids = set(sites_by_id)
    relevant_alarms = [
        alarm for alarm in alarms
        if not impacted_site_ids or str(alarm.get("Site ID") or "").strip() in impacted_site_ids
    ]
    if not relevant_alarms:
        relevant_alarms = site_rows

    occurrences = [
        alarm.get("Occurrence Time") for alarm in relevant_alarms
        if isinstance(alarm.get("Occurrence Time"), datetime)
    ]
    clear_times = [
        alarm.get("Clear Time") for alarm in relevant_alarms
        if isinstance(alarm.get("Clear Time"), datetime)
    ]
    start_time = min(occurrences, default=None)
    end_time = max(clear_times, default=None)
    is_open = any(
        alarm.get("Alarm State") == "Active" or alarm.get("Clear Time") is None
        for alarm in relevant_alarms
    )

    providers = sorted({
        str(row.get("VSAT Provider") or "").strip()
        for row in [*site_rows, *summaries]
        if str(row.get("VSAT Provider") or "").strip()
    })
    packages = sorted({
        str(site.get("Paket") or "").strip()
        for site in sites_by_id.values()
        if str(site.get("Paket") or "").strip()
    })
    areas = sorted({
        str(site.get("Area") or "").strip()
        for site in sites_by_id.values()
        if str(site.get("Area") or "").strip()
    })
    transmission_vendors = list(dict.fromkeys(
        str(site.get("Vendor Transmisi") or "").strip()
        for site in sites_by_id.values()
        if str(site.get("Vendor Transmisi") or "").strip()
    ))
    if not transmission_vendors:
        transmission_vendors = list(dict.fromkeys(
            str(alarm.get("Vendor Transmisi") or "").strip()
            for alarm in relevant_alarms
            if str(alarm.get("Vendor Transmisi") or "").strip()
        ))
    transmission_vendor_text = ", ".join(transmission_vendors) or "-"
    package_text = ", ".join(packages) if packages else "-"
    area_text = ", ".join(areas) if areas else "AREA"
    provider_text = ", ".join(providers) if providers else "Unknown"
    site_count = len(sites_by_id)

    bapl_count = sum(
        str(site.get("Status BAPL") or "").strip().upper() == "BAPL"
        for site in sites_by_id.values()
    )
    non_bapl_count = site_count - bapl_count
    status = "OPEN" if is_open else "CLOSED"
    start_text = _format_datetime(start_time) if start_time else "-"
    end_text = _format_datetime(end_time) if end_time else "ONGOING"
    title = (
        f"Massive Problem [PT. LINDU PUTRA UTAMA] {site_count} SITES VSAT DOWN "
        f"PAKET {package_text} {area_text} UNDER {provider_text}"
    )
    text = "\n".join([
        "Service Incident TT :",
        "ID Tiket KSO : -",
        "ID Tiket Bakti OSS : -",
        "",
        title,
        f"Status : {status}",
        f"Start time : {start_text}",
        f"End time : {end_text}",
        "",
        "Site Impacted :",
        f"{site_count} Site ({bapl_count} BAPL, {non_bapl_count} non BAPL)",
        "",
        "Rootcause : -",
        "",
        f"PIC Incident : {transmission_vendor_text}",
        f"PIC Vendor Transmisi : {transmission_vendor_text}",
        "",
        "Update :",
        f"-[{start_text}] Alarm massive appear",
        f"-[{end_text}] Alarm Clear" if not is_open else f"-[{end_text}] Alarm still active",
        "",
        "RCA : -",
        "Action : Autorecovery",
    ])
    return text


def _unique_site_breakdown(site_rows: list[dict], field: str) -> list[tuple[str, int]]:
    unique_sites: dict[str, dict] = {}
    for site in site_rows:
        site_id = str(site.get("Site ID") or "").strip()
        if site_id:
            unique_sites.setdefault(site_id, site)

    counts: dict[str, int] = {}
    for site in unique_sites.values():
        value = str(site.get(field) or "Unknown").strip() or "Unknown"
        counts[value] = counts.get(value, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def _format_elapsed_hms(seconds: int) -> str:
    hours, remainder = divmod(max(seconds, 0), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _add_executive_summary_sheet(workbook: Workbook, alarms: list[dict], site_rows: list[dict]) -> None:
    sheet = workbook.create_sheet("Executive Summary", 0)
    unique_sites: dict[str, dict] = {}
    for site in site_rows:
        site_id = str(site.get("Site ID") or "").strip()
        if site_id:
            unique_sites.setdefault(site_id, site)
    site_ids = set(unique_sites)
    relevant_alarms = [
        alarm for alarm in alarms
        if not site_ids or str(alarm.get("Site ID") or "").strip() in site_ids
    ]
    if not relevant_alarms:
        relevant_alarms = site_rows

    metric_sites = list(unique_sites.values()) or relevant_alarms
    occurrences = [
        site["Occurrence Time"] for site in metric_sites
        if isinstance(site.get("Occurrence Time"), datetime)
    ]
    clear_times = [
        site["Clear Time"] for site in metric_sites
        if isinstance(site.get("Clear Time"), datetime)
    ]
    first_occurrence = min(occurrences, default=None)
    last_clear = max(clear_times, default=None)
    still_active = any(
        site.get("Alarm State") == "Active" or site.get("Clear Time") is None
        for site in metric_sites
    )
    end_time = None if still_active else last_clear
    elapsed = end_time - first_occurrence if end_time and first_occurrence else None
    bapl_count = sum(
        str(site.get("Status BAPL") or "").strip().casefold() == "bapl"
        for site in unique_sites.values()
    )
    non_bapl_count = len(unique_sites) - bapl_count

    package_names = sorted({
        str(site.get("Paket") or "").strip()
        for site in unique_sites.values()
        if str(site.get("Paket") or "").strip()
    })
    area_names = sorted({
        str(site.get("Area") or "").strip()
        for site in unique_sites.values()
        if str(site.get("Area") or "").strip()
    })
    transmission_vendors = sorted({
        str(site.get("Vendor Transmisi") or "").strip()
        for site in unique_sites.values()
        if str(site.get("Vendor Transmisi") or "").strip()
    })
    satellites = sorted({
        str(site.get("VSAT Provider") or "").strip()
        for site in unique_sites.values()
        if str(site.get("VSAT Provider") or "").strip()
    })
    vendor_order = {"ZTE": 0, "Fiberhome": 1, "Huawei": 2}
    alarm_vendors = sorted(
        {
            str(site.get("Vendor") or "").strip() or "Unknown"
            for site in unique_sites.values()
        },
        key=lambda vendor: (vendor_order.get(vendor, 3), vendor.casefold()),
    )
    sites_by_alarm_vendor = {
        vendor: sum(
            (str(site.get("Vendor") or "").strip() or "Unknown") == vendor
            for site in unique_sites.values()
        )
        for vendor in alarm_vendors
    }

    downtime_by_site: dict[str, int] = {}
    for site_id, site in unique_sites.items():
        occurrence = site.get("Occurrence Time")
        clear_time = site.get("Clear Time")
        seconds = site.get("Duration Seconds")
        if not isinstance(seconds, (int, float)) and (
            isinstance(occurrence, datetime) and isinstance(clear_time, datetime)
        ):
            seconds = (clear_time - occurrence).total_seconds()
        if isinstance(seconds, (int, float)) and seconds >= 0:
            downtime_by_site[site_id] = int(seconds)
    average_downtime = (
        round(sum(downtime_by_site.values()) / len(downtime_by_site))
        if downtime_by_site else None
    )

    dark_teal = "0E4D5A"
    light_blue = "D9EAF0"
    black = "000000"
    white = "FFFFFF"
    thin_black = Side(style="thin", color=black)
    box_border = Border(
        left=thin_black,
        right=thin_black,
        top=thin_black,
        bottom=thin_black,
    )

    sheet.merge_cells("A1:E1")
    sheet["A1"] = "EXECUTIVE SUMMARY | VSAT OUTAGE"
    sheet["A1"].font = Font(name="Arial", bold=True, color=white, size=16)
    sheet["A1"].fill = PatternFill("solid", fgColor=dark_teal)
    sheet["A1"].alignment = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[1].height = 27

    package_value: int | str = ", ".join(package_names) or "-"
    if len(package_names) == 1 and package_names[0].isdigit():
        package_value = int(package_names[0])
    left_fields = [
        ("Paket", package_value),
        ("Area", ", ".join(area_names) or "-"),
        ("Vendor Transmisi", ", ".join(transmission_vendors) or "-"),
        ("Satellite", ", ".join(satellites) or "-"),
        ("Unique impacted sites", len(unique_sites)),
        ("BAPL", bapl_count),
        ("Non BAPL", non_bapl_count),
    ]
    right_fields = [
        *((f"Total Site {vendor}", count) for vendor, count in sites_by_alarm_vendor.items()),
        ("Alarm Occurrence", _format_datetime(first_occurrence) or "-"),
        ("Alarm Clear", _format_datetime(last_clear) if last_clear and not still_active else ("ONGOING" if still_active else "-")),
        ("Incident duration", _format_elapsed_hms(int(elapsed.total_seconds())) if elapsed else ("ONGOING" if still_active else "-")),
        ("Average BTS Downtime", _format_elapsed_hms(average_downtime) if average_downtime is not None else "-"),
    ]
    metrics_count = max(len(left_fields), len(right_fields))
    for offset in range(metrics_count):
        row_number = offset + 2
        for column, fields in ((1, left_fields), (4, right_fields)):
            if offset >= len(fields):
                continue
            label, value = fields[offset]
            label_cell = sheet.cell(row_number, column, label)
            value_cell = sheet.cell(row_number, column + 1, value)
            label_cell.font = Font(name="Arial", bold=True, size=11)
            label_cell.border = box_border
            label_cell.alignment = Alignment(vertical="center")
            value_cell.border = box_border
            value_cell.alignment = Alignment(
                horizontal="right" if isinstance(value, (int, float)) else "left",
                vertical="center",
            )
        sheet.row_dimensions[row_number].height = 18

    region_header_row = metrics_count + 3
    region_columns_row = region_header_row + 1
    sheet.merge_cells(start_row=region_header_row, start_column=1, end_row=region_header_row, end_column=3)
    sheet.cell(region_header_row, 1, "REGION")
    sheet.cell(region_header_row, 1).font = Font(name="Arial", bold=True, color=white, size=11)
    sheet.cell(region_header_row, 1).fill = PatternFill("solid", fgColor=dark_teal)
    sheet.cell(region_header_row, 1).alignment = Alignment(horizontal="center", vertical="center")
    for col in range(1, 4):
        sheet.cell(region_header_row, col).fill = PatternFill("solid", fgColor=dark_teal)
        sheet.cell(region_header_row, col).border = box_border
    sheet.row_dimensions[region_header_row].height = 20

    for col, value in enumerate(("Region", "Unique Sites", "Share"), start=1):
        cell = sheet.cell(region_columns_row, col, value)
        cell.font = Font(name="Arial", bold=True, size=11)
        cell.fill = PatternFill("solid", fgColor=light_blue)
        cell.border = box_border
        cell.alignment = Alignment(vertical="center")
    sheet.row_dimensions[region_columns_row].height = 18

    regions = _unique_site_breakdown(site_rows, "Region")
    for row_number, (region, count) in enumerate(regions, start=region_columns_row + 1):
        sheet.cell(row_number, 1, region)
        count_cell = sheet.cell(row_number, 2, count)
        share_cell = sheet.cell(row_number, 3, count / len(unique_sites) if unique_sites else 0)
        share_cell.number_format = "0.0%"
        for col in range(1, 4):
            sheet.cell(row_number, col).font = Font(name="Arial", size=11)
            sheet.cell(row_number, col).border = box_border
            sheet.cell(row_number, col).alignment = Alignment(
                horizontal="right" if col in (2, 3) else "left",
                vertical="center",
            )
        count_cell.number_format = "0"
        sheet.row_dimensions[row_number].height = 18

    for column, width in {"A": 40, "B": 22.5, "C": 7, "D": 38, "E": 22.5}.items():
        sheet.column_dimensions[column].width = width
    sheet.sheet_view.showGridLines = True
    sheet.sheet_view.zoomScale = 100


def save_report(path: str | Path, alarms: list[dict], summaries: list[dict]) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    impact_rows = _selected_site_report_rows(alarms, summaries)
    _add_executive_summary_sheet(workbook, alarms, impact_rows)

    def add_sheet(name: str, headers: list[str], rows: list[dict]) -> None:
        sheet = workbook.create_sheet(name)
        sheet.append(headers)
        for row in rows:
            sheet.append([row.get(header, "") for header in headers])
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="0E4D5A")
            cell.alignment = Alignment(vertical="center")
        for column in sheet.columns:
            values = [len(str(cell.value or "")) for cell in column[:150]]
            sheet.column_dimensions[column[0].column_letter].width = min(max(max(values, default=10) + 2, 12), 44)

    # 1. Sheet 1: Consolidated Alarms History
    add_sheet("Consolidated Alarms", NORMALIZED_COLUMNS, alarms)

    # 2. Sheet 2: VSAT Summary
    add_sheet("VSAT Summary", SUMMARY_REPORT_COLUMNS, _summary_report_rows(summaries))

    # 3. Original Raw Alarms sheet per vendor: "Alarm Original - <Vendor>"
    vendors: list[str] = []
    for a in alarms:
        v = (a.get("Vendor") or "").strip() or "Unknown"
        if v not in vendors:
            vendors.append(v)
    for vendor in vendors:
        v_alarms = [
            a for a in alarms
            if ((a.get("Vendor") or "").strip() or "Unknown") == vendor
        ]
        _, raw_headers = _raw_alarm_rows_and_headers(v_alarms)
        v_alarms.sort(key=lambda a: a.get("Occurrence Time") or datetime.min)
        v_raw_rows, _ = _raw_alarm_rows_and_headers(v_alarms)
        if not raw_headers:
            raw_headers = list(NORMALIZED_COLUMNS)

        sheet_title = _safe_sheet_title(f"Alarm Original - {vendor}")
        sheet_raw = workbook.create_sheet(sheet_title)
        sheet_raw.append(raw_headers)
        for r in v_raw_rows:
            sheet_raw.append([r.get(h, "") if r.get(h) is not None else "" for h in raw_headers])
        _style_report_sheet(sheet_raw, "1E3A5F")

    workbook.save(path)


def _summary_report_rows(summaries: list[dict]) -> list[dict]:
    return [
        {
            **{key: value for key, value in summary.items() if key != "Sites at Peak"},
            "Massive Down": "YES" if summary.get("Massive Down") else "NO",
            "Sites at Peak": ", ".join(summary["Sites at Peak"]),
        }
        for summary in summaries
    ]


def _report_data_for_selection(
    alarms: list[dict],
    summaries: list[dict],
    selected_alarm_names: set[str],
    selected_vsats: set[str],
    selected_alarm_types: set[str],
    range_start: datetime,
    range_end: datetime,
    selected_summary_keys: set[tuple[str, ...]] | None = None,
    group_by_spotbeam: bool = False,
) -> tuple[list[dict], list[dict]]:
    def summary_selected(summary: dict) -> bool:
        if selected_summary_keys is None:
            return True
        provider = summary["VSAT Provider"]
        spotbeam = summary["Spotbeam"]
        peak_key = (provider, spotbeam, _format_datetime(summary.get("Peak Time")))
        legacy_key = (provider, spotbeam)
        return peak_key in selected_summary_keys or legacy_key in selected_summary_keys

    selected_summaries = [
        summary for summary in summaries
        if summary["VSAT Provider"] in selected_vsats
        and summary_selected(summary)
    ]
    selected_groups = {
        (summary["VSAT Provider"], summary["Spotbeam"])
        for summary in selected_summaries
    }
    selected_providers = {summary["VSAT Provider"] for summary in selected_summaries}
    filtered_alarms = [
        alarm for alarm in alarms
        if alarm["Alarm Name"] in selected_alarm_names
        and (alarm["VSAT Provider"] or "Unknown") in selected_vsats
        and (alarm["Alarm Type"] or "Unknown") in selected_alarm_types
        and (alarm["VSAT Provider"] or "Unknown") in selected_providers
        and (
            not group_by_spotbeam
            or (
                alarm["VSAT Provider"] or "Unknown",
                alarm["Spotbeam"] or "Unknown",
            ) in selected_groups
        )
        and _alarm_overlaps_range(alarm, range_start, range_end)
    ]
    return filtered_alarms, selected_summaries


def _selected_site_report_rows(
    alarms: list[dict],
    summaries: list[dict],
    incident_window_minutes: int = 45,
) -> list[dict]:
    sites: dict[tuple[str, str, datetime | None, str], dict] = {}
    for summary in summaries:
        provider = summary["VSAT Provider"]
        spotbeam = summary["Spotbeam"]
        peak_time = summary.get("Peak Time")
        if peak_time is not None:
            window_start = peak_time - timedelta(minutes=incident_window_minutes)
            window_end = peak_time + timedelta(minutes=15)
        else:
            window_start = datetime.min
            window_end = datetime.max

        for site_id in summary.get("Sites at Peak", []):
            site_key = (provider, spotbeam, peak_time, site_id)
            if site_key in sites:
                continue
            candidates = [
                alarm for alarm in alarms
                if alarm["Site ID"] == site_id
                and (alarm["VSAT Provider"] or "Unknown") == provider
                and (not spotbeam or (alarm["Spotbeam"] or "Unknown") == spotbeam)
            ]
            active_at_peak = [
                alarm for alarm in candidates
                if peak_time is not None
                and alarm["Occurrence Time"] <= peak_time
                and (alarm["Clear Time"] is None or alarm["Clear Time"] > peak_time)
            ]
            incident_candidates = [
                alarm for alarm in (active_at_peak or candidates)
                if window_start <= alarm["Occurrence Time"] <= window_end
            ]
            # Skip isolated pre-existing down sites whose alarm occurred hours/days ago
            if not incident_candidates:
                continue

            representative = max(
                incident_candidates,
                key=lambda alarm: alarm["Occurrence Time"],
                default={},
            )
            sites[site_key] = {
                **{column: representative.get(column, "") for column in NORMALIZED_COLUMNS},
                "Site ID": site_id,
                "VSAT Provider": representative.get("VSAT Provider", provider),
                "Vendor": representative.get("Vendor") or "Unknown",
                "Paket": representative.get("Paket") or "",
                "Area": representative.get("Area") or "",
                "_peak_time": peak_time,
                "_summary_spotbeam": spotbeam,
                "_raw": representative.get("_raw", {}),
            }

    # Fallback if no sites matched the window (e.g. synthetic test data)
    if not sites:
        for summary in summaries:
            provider = summary["VSAT Provider"]
            spotbeam = summary["Spotbeam"]
            peak_time = summary.get("Peak Time")
            for site_id in summary.get("Sites at Peak", []):
                site_key = (provider, spotbeam, peak_time, site_id)
                if site_key in sites:
                    continue
                candidates = [
                    alarm for alarm in alarms
                    if alarm["Site ID"] == site_id
                    and (alarm["VSAT Provider"] or "Unknown") == provider
                    and (not spotbeam or (alarm["Spotbeam"] or "Unknown") == spotbeam)
                ]
                active_at_peak = [
                    alarm for alarm in candidates
                    if peak_time is not None
                    and alarm["Occurrence Time"] <= peak_time
                    and (alarm["Clear Time"] is None or alarm["Clear Time"] > peak_time)
                ]
                representative = max(
                    active_at_peak or candidates,
                    key=lambda alarm: alarm["Occurrence Time"],
                    default={},
                )
                sites[site_key] = {
                    **{column: representative.get(column, "") for column in NORMALIZED_COLUMNS},
                    "Site ID": site_id,
                    "VSAT Provider": representative.get("VSAT Provider", provider),
                    "Vendor": representative.get("Vendor") or "Unknown",
                    "Paket": representative.get("Paket") or "",
                    "Area": representative.get("Area") or "",
                    "_peak_time": peak_time,
                    "_summary_spotbeam": spotbeam,
                    "_raw": representative.get("_raw", {}),
                }

    return [{"No": index, **row} for index, row in enumerate(sites.values(), start=1)]


def _suggested_selected_export_filename(
    selected_summaries: list[dict],
    selected_site_rows: list[dict],
    range_start: datetime | None = None,
) -> str:
    count = len(selected_site_rows)
    # Collect unique providers in order
    providers: list[str] = []
    for s in selected_summaries:
        p = (s.get("VSAT Provider") or "").strip()
        if p and p not in providers:
            providers.append(p)
    if not providers:
        for r in selected_site_rows:
            p = (r.get("VSAT Provider") or "").strip()
            if p and p not in providers:
                providers.append(p)
    providers_str = " & ".join(providers) if providers else "UNKNOWN"

    # Paket
    pakets = {r.get("Paket", "").strip() for r in selected_site_rows if r.get("Paket")}
    paket_part = ""
    if len(pakets) == 1:
        p_val = next(iter(pakets))
        paket_part = p_val if p_val.upper().startswith("PAKET") else f"PAKET {p_val}"

    # Area / Region
    areas = {r.get("Area", "").strip() for r in selected_site_rows if r.get("Area")}
    if not areas:
        areas = {r.get("Region", "").strip() for r in selected_site_rows if r.get("Region")}
    area_part = ""
    if len(areas) == 1:
        a_val = next(iter(areas))
        area_part = a_val if a_val.upper().startswith("AREA") else f"AREA {a_val}"

    # Date
    date_val = None
    for s in selected_summaries:
        if s.get("Peak Time"):
            date_val = s["Peak Time"]
            break
    if not date_val and range_start:
        date_val = range_start
    if not date_val:
        date_val = datetime.now()
    date_str = date_val.strftime("%Y%m%d")

    parts = [f"{count} SITES VSAT DOWN"]
    if paket_part:
        parts.append(paket_part.upper())
    if area_part:
        parts.append(area_part.upper())
    parts.append(f"UNDER {providers_str.upper()}")
    parts.append(date_str)

    filename = " ".join(parts).strip() + ".xlsx"
    return re.sub(r'[\\/*?:"<>|]', '_', filename)


def _safe_sheet_title(name: str) -> str:
    cleaned = re.sub(r'[\\/*?:\[\]]', '_', str(name or "")).strip()
    return cleaned[:31] if cleaned else "Sheet"


def _style_report_sheet(sheet, header_bg: str = "0E4D5A") -> None:
    sheet.freeze_panes = "A2"
    if sheet.dimensions:
        sheet.auto_filter.ref = sheet.dimensions
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=header_bg)
        cell.alignment = Alignment(vertical="center")
    for column in sheet.columns:
        values = [len(str(cell.value or "")) for cell in column[:150]]
        sheet.column_dimensions[column[0].column_letter].width = min(max(max(values, default=10) + 2, 12), 44)


def _raw_alarm_rows_and_headers(alarms: list[dict]) -> tuple[list[dict], list[str]]:
    raw_rows = []
    for alarm in alarms:
        raw = alarm.get("_raw")
        if isinstance(raw, dict) and raw:
            raw_rows.append(raw)
        else:
            raw_rows.append({
                key: value for key, value in alarm.items()
                if not str(key).startswith("_")
            })

    headers: list[str] = []
    if raw_rows:
        headers.extend(
            key for key in raw_rows[0]
            if not str(key).startswith("_")
        )
    known_headers = set(headers)
    for raw in raw_rows[1:]:
        for key in raw:
            if not str(key).startswith("_") and key not in known_headers:
                headers.append(key)
                known_headers.add(key)
    return raw_rows, headers


def save_selected_site_report(path: str | Path, alarms: list[dict], summaries: list[dict]) -> None:
    all_site_rows = _selected_site_report_rows(alarms, summaries)
    selected_site_ids = {row["Site ID"] for row in all_site_rows if row.get("Site ID")}
    if not selected_site_ids:
        selected_site_ids = {s for sum_item in summaries for s in sum_item.get("Sites at Peak", []) if s}

    workbook = Workbook()
    workbook.remove(workbook.active)
    _add_executive_summary_sheet(workbook, alarms, all_site_rows)

    # 1. Sheet "Site Impact Massive" (All selected converted sites consolidated)
    sheet_sites = workbook.create_sheet("Site Impact Massive")
    headers = ["No", *NORMALIZED_COLUMNS]
    sheet_sites.append(headers)
    for row in all_site_rows:
        sheet_sites.append([row.get(h, "") for h in headers])
    _style_report_sheet(sheet_sites, "0E4D5A")

    # Determine vendors present in the selection
    vendors: list[str] = []
    for row in all_site_rows:
        v = (row.get("Vendor") or "").strip() or "Unknown"
        if v not in vendors:
            vendors.append(v)
    if not vendors:
        for a in alarms:
            v = (a.get("Vendor") or "").strip() or "Unknown"
            if v not in vendors:
                vendors.append(v)
    if not vendors:
        vendors = ["Unknown"]

    # Calculate incident window for raw alarm sheets
    peak_times = [s["Peak Time"] for s in summaries if s.get("Peak Time")]
    if peak_times:
        earliest_peak = min(peak_times)
        latest_peak = max(peak_times)
        incident_start = earliest_peak - timedelta(minutes=45)
        incident_end = latest_peak + timedelta(minutes=60)
    else:
        incident_start = datetime.min
        incident_end = datetime.max

    # 2. Original Raw Alarms sheet per vendor: "Alarm Original - <Vendor>"
    for vendor in vendors:
        v_alarms = [
            a for a in alarms
            if ((a.get("Vendor") or "").strip() or "Unknown") == vendor
            and (not selected_site_ids or a.get("Site ID") in selected_site_ids)
            and incident_start <= (a.get("Occurrence Time") or datetime.min) <= incident_end
        ]
        # Fallback if window filtering yielded no alarms
        if not v_alarms:
            v_alarms = [
                a for a in alarms
                if ((a.get("Vendor") or "").strip() or "Unknown") == vendor
                and (not selected_site_ids or a.get("Site ID") in selected_site_ids)
            ]
        _, raw_headers = _raw_alarm_rows_and_headers(v_alarms)
        # Chronological sort by occurrence time
        v_alarms.sort(key=lambda a: a.get("Occurrence Time") or datetime.min)

        # Collect raw records without altering anything or dropping duplicates
        v_raw_rows, _ = _raw_alarm_rows_and_headers(v_alarms)
        if not raw_headers:
            raw_headers = list(NORMALIZED_COLUMNS)

        sheet_title = _safe_sheet_title(f"Alarm Original - {vendor}")
        sheet_raw = workbook.create_sheet(sheet_title)
        sheet_raw.append(raw_headers)
        for r in v_raw_rows:
            sheet_raw.append([r.get(h, "") if r.get(h) is not None else "" for h in raw_headers])
        _style_report_sheet(sheet_raw, "1E3A5F")

    workbook.save(path)


class AlarmNameFilterDialog(QDialog):
    def __init__(self, parent: QWidget, alarm_names: list[str], selected: set[str], current_theme: dict):
        super().__init__(parent)
        self.setObjectName("filterDialog")
        self.setWindowTitle("Filter by Alarm Name")
        self.resize(460, 540)
        self.current_theme = current_theme

        dialog_bg = current_theme.get("app_bg", "#0a0e17")
        card_bg = current_theme.get("card_bg", "#111827")
        text_color = current_theme.get("text", "#f8fafc")
        border_color = current_theme.get("border", "#1f2d42")
        accent_color = current_theme.get("accent", "#06b6d4")

        self.setStyleSheet(current_theme["qss"] + f"""
            QDialog, QDialog#filterDialog {{
                background-color: {dialog_bg};
                color: {text_color};
            }}
            QScrollArea {{
                background-color: {card_bg};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
            QWidget#checkboxContainer {{
                background-color: {card_bg};
            }}
            QCheckBox {{
                color: {text_color};
                font-size: 12px;
                padding: 4px 2px;
            }}
            QCheckBox:hover {{
                color: {accent_color};
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {border_color};
                border-radius: 4px;
                background-color: {dialog_bg};
            }}
            QCheckBox::indicator:checked {{
                background-color: {accent_color};
                border-color: {accent_color};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("FILTER BY ALARM NAME")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search alarm name...")
        self.search_edit.textChanged.connect(self._filter_checkboxes)
        layout.addWidget(self.search_edit)

        action_layout = QHBoxLayout()
        self.btn_all = QPushButton("Select All")
        self.btn_all.setObjectName("pillBtn")
        self.btn_all.clicked.connect(self._select_all)
        self.btn_clear = QPushButton("Clear All")
        self.btn_clear.setObjectName("pillBtn")
        self.btn_clear.clicked.connect(self._clear_all)
        action_layout.addWidget(self.btn_all)
        action_layout.addWidget(self.btn_clear)
        action_layout.addStretch()
        layout.addLayout(action_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        container.setObjectName("checkboxContainer")
        self.checkbox_layout = QVBoxLayout(container)
        self.checkbox_layout.setContentsMargins(6, 6, 6, 6)
        self.checkbox_layout.setSpacing(4)

        self.checkboxes: dict[str, QCheckBox] = {}
        for name in alarm_names:
            cb = QCheckBox(name)
            cb.setChecked(name in selected)
            self.checkboxes[name] = cb
            self.checkbox_layout.addWidget(cb)
        self.checkbox_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        btn_done = QPushButton("Apply & Close")
        btn_done.setObjectName("accentBtn")
        btn_done.clicked.connect(self.accept)
        bottom_layout.addWidget(btn_done)
        layout.addLayout(bottom_layout)

    def _filter_checkboxes(self, query: str):
        q = query.strip().casefold()
        for name, cb in self.checkboxes.items():
            cb.setVisible(q in name.casefold())

    def _select_all(self):
        for cb in self.checkboxes.values():
            if cb.isVisible():
                cb.setChecked(True)

    def _clear_all(self):
        for cb in self.checkboxes.values():
            if cb.isVisible():
                cb.setChecked(False)

    def get_selected(self) -> set[str]:
        return {name for name, cb in self.checkboxes.items() if cb.isChecked()}


class AnalysisWorker(QThread):
    progress_stage = pyqtSignal(str, int)
    finished_success = pyqtSignal(list, list)
    finished_error = pyqtSignal(str)

    def __init__(self, master_path: Path, vendor_paths: list[tuple[str, Path]]):
        super().__init__()
        self.master_path = master_path
        self.vendor_paths = vendor_paths

    def run(self):
        try:
            self.progress_stage.emit("Reading Site Management master database...", 15)
            master_raw = self.master_path.read_bytes()
            master_rows = read_table(master_raw, self.master_path.name)
            self.progress_stage.emit("Indexing site catalog and spotbeams...", 30)
            site_index = build_site_index(master_rows)
            site_count = len(site_index)

            self.progress_stage.emit(f"Master index ready ({site_count:,} sites). Parsing alarms...", 40)

            alarms = []
            imported = []
            total_feeds = len(self.vendor_paths)
            for idx, (expected_slot, path) in enumerate(self.vendor_paths):
                feed_base_pct = 40 + int((idx / max(total_feeds, 1)) * 40)
                self.progress_stage.emit(f"Reading {path.name} ({expected_slot})...", feed_base_pct)
                raw = path.read_bytes()
                rows = read_table(raw, path.name)
                vendor = detect_alarm_vendor(rows)
                if vendor is None:
                    raise ValueError(
                        f"Unrecognized alarm headers in {path.name}. "
                        "Ensure the file contains supported ZTE, Fiberhome, or Huawei columns."
                    )
                self.progress_stage.emit(f"Normalizing {len(rows):,} {vendor} records...", feed_base_pct + 18)
                normalized = normalize_alarms(rows, site_index, vendor)
                alarms.extend(normalized)
                imported.append((vendor, path.name, len(rows), len(normalized)))

            if not alarms:
                raise ValueError("No alarms could be matched to Site IDs in Site Management.")

            self.progress_stage.emit("Cross-vendor timeline correlation ready.", 95)
            self.finished_success.emit(alarms, imported)
        except Exception as exc:
            self.finished_error.emit(str(exc))


class MassiveSiteDownApp(QMainWindow):
    def __init__(self):
        super().__init__()
        apply_standard_window_chrome(self)
        self._close_pending = False
        self.setWindowTitle("NOC Tools | Massive Checker")
        self.resize(1400, 850)

        application = QApplication.instance()
        self.current_theme_name = (
            application.property("nocTheme") if application else None
        ) or system_theme_name(application)
        if application is not None:
            set_application_theme(self.current_theme_name, application)
        self.setWindowIcon(app_icon(self.current_theme_name))

        self.alarms: list[dict] = []
        self.imported: list[tuple[str, str, int, int]] = []
        self.summaries: list[dict] = []
        self.selected_vsats: set[str] = set()
        self.selected_alarm_types: set[str] = set()
        self.selected_alarm_names: set[str] = set()
        self.all_alarm_names: list[str] = []

        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(70)
        self._spinner_timer.timeout.connect(self._cycle_spinner)
        self._spinner_frame_idx = 0
        self._current_progress_msg = "Ready"
        self.worker: AnalysisWorker | None = None

        default_alarm_paths = self._default_alarm_paths()
        self.path_zte = str(default_alarm_paths.get("ZTE", ""))
        self.path_fiberhome = str(default_alarm_paths.get("Fiberhome", ""))
        self.path_huawei = str(default_alarm_paths.get("Huawei", ""))
        self.master_mode = "default"
        self.master_custom_path = ""

        self._build_ui()
        self._apply_theme(self.current_theme_name)

        if DEFAULT_MASTER_PATH.is_file() and (self.path_zte or self.path_fiberhome or self.path_huawei):
            self.load_and_analyze()

    @staticmethod
    def _default_alarm_paths() -> dict[str, Path]:
        supported_extensions = {".zip", ".xlsx", ".xlsm", ".xls", ".csv", ".txt", ".dat", ".bin"}
        latest: dict[str, tuple[float, Path]] = {}
        for path in BASE_DIR.iterdir():
            if not path.is_file() or path.suffix.casefold() not in supported_extensions:
                continue
            try:
                rows = read_table(path.read_bytes(), path.name)
                vendor = detect_alarm_vendor(rows)
                modified = path.stat().st_mtime
            except Exception:
                continue
            if vendor and (vendor not in latest or modified > latest[vendor][0]):
                latest[vendor] = (modified, path)
        return {vendor: item[1] for vendor, item in latest.items()}

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(14, 10, 14, 10)
        root_layout.setSpacing(10)

        # Header Deck (Clean & Sleek without Live Radar / Subtitle)
        header_frame = QFrame()
        header_frame.setObjectName("headerCard")
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(10, 4, 10, 4)

        logo = NocLogoMark(32)
        h_layout.addWidget(logo)

        title_label = QLabel("NOC TOOLS  /  MASSIVE CHECKER")
        title_label.setObjectName("headerTitle")
        h_layout.addWidget(title_label)

        h_layout.addStretch()

        self.theme_selector = ThemeSelector(self.current_theme_name)
        self.theme_selector.themeChanged.connect(self._apply_theme)
        h_layout.addWidget(self.theme_selector)

        root_layout.addWidget(header_frame)

        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.setHandleWidth(8)

        # Left Sidebar (Controls)
        sidebar = QFrame()
        sidebar.setObjectName("card")
        sidebar.setMinimumWidth(0)
        sidebar.setMaximumWidth(420)
        s_layout = QVBoxLayout(sidebar)
        s_layout.setContentsMargins(14, 14, 14, 14)
        s_layout.setSpacing(12)

        # Section 1: Alarm Data Feeds
        feed_title = QLabel("ALARM DATA FEEDS")
        feed_title.setObjectName("sectionTitle")
        s_layout.addWidget(feed_title)

        # ZTE feed
        s_layout.addWidget(QLabel("ZTE Export:"))
        zte_row = QHBoxLayout()
        self.edit_zte = QLineEdit(Path(self.path_zte).name if self.path_zte else "")
        self.edit_zte.setReadOnly(True)
        self.btn_browse_zte = QPushButton("Browse...")
        self.btn_browse_zte.setObjectName("pillBtn")
        self.btn_browse_zte.clicked.connect(lambda: self._choose_alarm_file("ZTE"))
        zte_row.addWidget(self.edit_zte)
        zte_row.addWidget(self.btn_browse_zte)
        s_layout.addLayout(zte_row)

        # Fiberhome feed
        s_layout.addWidget(QLabel("Fiberhome Export:"))
        fh_row = QHBoxLayout()
        self.edit_fh = QLineEdit(Path(self.path_fiberhome).name if self.path_fiberhome else "")
        self.edit_fh.setReadOnly(True)
        self.btn_browse_fh = QPushButton("Browse...")
        self.btn_browse_fh.setObjectName("pillBtn")
        self.btn_browse_fh.clicked.connect(lambda: self._choose_alarm_file("Fiberhome"))
        fh_row.addWidget(self.edit_fh)
        fh_row.addWidget(self.btn_browse_fh)
        s_layout.addLayout(fh_row)

        # Huawei feed
        s_layout.addWidget(QLabel("Huawei Export:"))
        hw_row = QHBoxLayout()
        self.edit_hw = QLineEdit(Path(self.path_huawei).name if self.path_huawei else "")
        self.edit_hw.setReadOnly(True)
        self.btn_browse_hw = QPushButton("Browse...")
        self.btn_browse_hw.setObjectName("pillBtn")
        self.btn_browse_hw.clicked.connect(lambda: self._choose_alarm_file("Huawei"))
        hw_row.addWidget(self.edit_hw)
        hw_row.addWidget(self.btn_browse_hw)
        s_layout.addLayout(hw_row)

        # Section 2: Master Site Database
        master_title = QLabel("SITE MANAGEMENT MASTER")
        master_title.setObjectName("sectionTitle")
        s_layout.addWidget(master_title)

        self.rb_master_default = QRadioButton("Default Master (1,404 Sites)")
        self.rb_master_default.setChecked(True)
        self.rb_master_default.toggled.connect(self._toggle_master_mode)
        s_layout.addWidget(self.rb_master_default)

        self.rb_master_custom = QRadioButton("Custom Master File")
        self.rb_master_custom.toggled.connect(self._toggle_master_mode)
        s_layout.addWidget(self.rb_master_custom)

        custom_row = QHBoxLayout()
        self.edit_custom_master = QLineEdit()
        self.edit_custom_master.setReadOnly(True)
        self.edit_custom_master.setEnabled(False)
        self.btn_browse_master = QPushButton("Browse...")
        self.btn_browse_master.setObjectName("pillBtn")
        self.btn_browse_master.setEnabled(False)
        self.btn_browse_master.clicked.connect(self._choose_master_file)
        custom_row.addWidget(self.edit_custom_master)
        custom_row.addWidget(self.btn_browse_master)
        s_layout.addLayout(custom_row)

        # Section 3: Detection Parameters
        param_title = QLabel("DETECTION PARAMETERS")
        param_title.setObjectName("sectionTitle")
        s_layout.addWidget(param_title)

        thresh_row = QHBoxLayout()
        thresh_lbl = QLabel("Massive Threshold (Sites):")
        thresh_lbl.setStyleSheet("font-weight: bold;")
        self.spin_threshold = QSpinBox()
        self.spin_threshold.setRange(2, 500)
        self.spin_threshold.setValue(5)
        thresh_row.addWidget(thresh_lbl)
        thresh_row.addWidget(self.spin_threshold)
        s_layout.addLayout(thresh_row)

        self.cb_spotbeam = QCheckBox("Breakdown results by Spotbeam")
        self.cb_spotbeam.stateChanged.connect(self.recalculate)
        s_layout.addWidget(self.cb_spotbeam)

        s_layout.addStretch()

        # Section 4: Primary Actions
        self.btn_run = QPushButton("▶ Run Analysis")
        self.btn_run.setObjectName("accentBtn")
        self.btn_run.setFixedHeight(38)
        self.btn_run.clicked.connect(self.load_and_analyze)
        s_layout.addWidget(self.btn_run)

        # Loading / Progress Deck with real-time animated feedback
        self.progress_deck = QFrame()
        self.progress_deck.setObjectName("progressDeck")
        self.progress_deck.setVisible(False)
        p_layout = QVBoxLayout(self.progress_deck)
        p_layout.setContentsMargins(6, 6, 6, 6)
        p_layout.setSpacing(4)

        p_info_row = QHBoxLayout()
        self.lbl_progress_status = QLabel("Analyzing...")
        self.lbl_progress_status.setStyleSheet("font-size: 11px; font-weight: bold;")
        self.lbl_progress_pct = QLabel("0%")
        self.lbl_progress_pct.setStyleSheet("font-size: 11px; font-weight: bold;")
        p_info_row.addWidget(self.lbl_progress_status)
        p_info_row.addStretch()
        p_info_row.addWidget(self.lbl_progress_pct)
        p_layout.addLayout(p_info_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        p_layout.addWidget(self.progress_bar)
        s_layout.addWidget(self.progress_deck)

        sub_actions = QHBoxLayout()
        self.btn_recalc = QPushButton("↻ Recalculate")
        self.btn_recalc.setToolTip("Recalculate metrics and filters using the current settings.")
        self.btn_recalc.clicked.connect(self.recalculate)
        self.btn_export = QPushButton("⬇ Export Excel")
        self.btn_export.setToolTip(
            "Export all analysis results to Excel.\n\n"
            "To export specific rows or providers, select rows in the "
            "'VSAT Outage Summary' table and right-click."
        )
        self.btn_export.clicked.connect(self.export_report)
        sub_actions.addWidget(self.btn_recalc)
        sub_actions.addWidget(self.btn_export)
        s_layout.addLayout(sub_actions)
        self.btn_reset_all = QPushButton("Reset All")
        self.btn_reset_all.setToolTip(
            "Clear alarm files, analysis results, filters, and custom master selection."
        )
        self.btn_reset_all.clicked.connect(self.reset_all_data)
        s_layout.addWidget(self.btn_reset_all)

        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.sidebar_scroll.setWidget(sidebar)
        self.sidebar_scroll.setMinimumWidth(340)
        self.sidebar_scroll.setMaximumWidth(440)
        self.workspace_splitter.addWidget(self.sidebar_scroll)

        # Right Workspace (Analytics & Intelligence Deck)
        right_deck = QVBoxLayout()
        right_deck.setSpacing(10)

        # Row 1: 3 Hero KPI Cards
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)

        self.metric_cards = []
        self.metric_vals = []
        kpi_specs = [
            ("AFFECTED SITES IN RANGE", "Active / cleared in selected window", "accent"),
            ("PEAK CONCURRENT DOWN", "Max simultaneous site outages", "signal"),
            ("MASSIVE OUTAGE INCIDENTS", "Providers exceeding threshold", "alert"),
        ]
        for title, sub, color_key in kpi_specs:
            card = QFrame()
            card.setObjectName("card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(2)

            t_lbl = QLabel(title)
            t_lbl.setObjectName("metricName")
            card_layout.addWidget(t_lbl)

            v_lbl = QLabel("-")
            v_lbl.setObjectName("metricValue")
            card_layout.addWidget(v_lbl)
            self.metric_vals.append(v_lbl)

            s_lbl = QLabel(sub)
            s_lbl.setObjectName("metricSub")
            card_layout.addWidget(s_lbl)

            kpi_row.addWidget(card)
            self.metric_cards.append((card, color_key))
        right_deck.addLayout(kpi_row)

        # Row 2: 2-Tier Structured Filter & Scope Deck (Guaranteed NEVER clipped)
        filter_card = QFrame()
        filter_card.setObjectName("card")
        f_layout = QVBoxLayout(filter_card)
        f_layout.setContentsMargins(14, 10, 14, 10)
        f_layout.setSpacing(8)

        # Tier 1: Filters & Presets
        tier1 = QHBoxLayout()
        tier1.setSpacing(8)

        lbl_filters = QLabel("FILTERS:")
        lbl_filters.setObjectName("filterTag")
        tier1.addWidget(lbl_filters)

        self.btn_vsat_filter = QPushButton("All VSAT Providers")
        self.btn_vsat_filter.setObjectName("pillBtn")
        self.menu_vsat = QMenu(self)
        self.btn_vsat_filter.setMenu(self.menu_vsat)
        tier1.addWidget(self.btn_vsat_filter)

        self.btn_type_filter = QPushButton("All Alarm Types")
        self.btn_type_filter.setObjectName("pillBtn")
        self.menu_type = QMenu(self)
        self.btn_type_filter.setMenu(self.menu_type)
        tier1.addWidget(self.btn_type_filter)

        self.btn_alarm_name_filter = QPushButton("All Alarms")
        self.btn_alarm_name_filter.setObjectName("pillBtn")
        self.btn_alarm_name_filter.clicked.connect(self._open_alarm_name_dialog)
        tier1.addWidget(self.btn_alarm_name_filter)

        tier1.addSpacing(12)
        lbl_presets = QLabel("PRESETS:")
        lbl_presets.setObjectName("filterTag")
        tier1.addWidget(lbl_presets)

        btn_today = QPushButton("Today")
        btn_today.setObjectName("pillBtn")
        btn_today.clicked.connect(self._preset_today)
        tier1.addWidget(btn_today)

        btn_last24 = QPushButton("Last 24h")
        btn_last24.setObjectName("pillBtn")
        btn_last24.clicked.connect(self._preset_last24h)
        tier1.addWidget(btn_last24)

        tier1.addStretch()
        f_layout.addLayout(tier1)

        # Tier 2: Time Scope Inputs & Apply Action
        tier2 = QHBoxLayout()
        tier2.setSpacing(8)

        lbl_start = QLabel("START TIME:")
        lbl_start.setObjectName("filterTag")
        tier2.addWidget(lbl_start)

        self.date_start = QDateEdit()
        self.date_start.setCalendarPopup(True)
        self.date_start.setDate(QDate.currentDate())
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        self.date_start.setMinimumWidth(135)
        tier2.addWidget(self.date_start)

        self.time_start = QTimeEdit()
        self.time_start.setTime(QTime(0, 0))
        self.time_start.setDisplayFormat("HH:mm")
        self.time_start.setMinimumWidth(80)
        tier2.addWidget(self.time_start)

        tier2.addSpacing(14)
        lbl_end = QLabel("END TIME:")
        lbl_end.setObjectName("filterTag")
        tier2.addWidget(lbl_end)

        self.date_end = QDateEdit()
        self.date_end.setCalendarPopup(True)
        self.date_end.setDate(QDate.currentDate())
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        self.date_end.setMinimumWidth(135)
        tier2.addWidget(self.date_end)

        self.time_end = QTimeEdit()
        self.time_end.setTime(QTime.currentTime())
        self.time_end.setDisplayFormat("HH:mm")
        self.time_end.setMinimumWidth(80)
        tier2.addWidget(self.time_end)

        tier2.addSpacing(14)
        # Prominent Apply Button with ample breathing room
        self.btn_apply = QPushButton("⟳ Apply Filter & Scope")
        self.btn_apply.setObjectName("accentBtn")
        self.btn_apply.setFixedHeight(32)
        self.btn_apply.clicked.connect(self.recalculate)
        tier2.addWidget(self.btn_apply)

        tier2.addStretch()
        f_layout.addLayout(tier2)

        right_deck.addWidget(filter_card)

        # Row 3: Tabbed Tables
        self.tabs = QTabWidget()
        self.tab_summary = QWidget()
        self.tab_alarms = QWidget()
        self.tab_sites = QWidget()

        self._setup_summary_tab()
        self._setup_alarms_tab()
        self._setup_sites_tab()

        self.tabs.addTab(self.tab_summary, "VSAT Outage Summary")
        self.tabs.addTab(self.tab_alarms, "Consolidated Alarms")
        self.tabs.addTab(self.tab_sites, "Sites at Peak Details")
        right_deck.addWidget(self.tabs, stretch=1)

        right_workspace = QWidget()
        right_workspace.setLayout(right_deck)
        self.workspace_splitter.addWidget(right_workspace)
        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setStretchFactor(1, 3)
        root_layout.addWidget(self.workspace_splitter, stretch=1)
        self.workspace_splitter.setSizes([340, 1060])

        # Bottom Telemetry Footer (Ultra-Compact)
        footer = QFrame()
        footer.setObjectName("footerCard")
        ft_layout = QHBoxLayout(footer)
        ft_layout.setContentsMargins(10, 3, 10, 3)

        self.lbl_footer_spinner = QLabel("●")
        self.lbl_footer_spinner.setObjectName("footerSpinner")
        self.lbl_footer_spinner.setFixedWidth(16)
        ft_layout.addWidget(self.lbl_footer_spinner)

        lbl_status_tag = QLabel("STATUS:")
        lbl_status_tag.setObjectName("statusTag")
        lbl_status_tag.setStyleSheet("font-weight: bold; font-size: 11px;")
        ft_layout.addWidget(lbl_status_tag)

        self.lbl_telemetry = QLabel("System Ready. Configure feeds or click Run Analysis.")
        self.lbl_telemetry.setObjectName("footerText")
        ft_layout.addWidget(self.lbl_telemetry, stretch=1)

        self.footer_progress = QProgressBar()
        self.footer_progress.setRange(0, 100)
        self.footer_progress.setValue(0)
        self.footer_progress.setTextVisible(False)
        self.footer_progress.setFixedSize(120, 6)
        self.footer_progress.setVisible(False)
        ft_layout.addWidget(self.footer_progress)

        self.btn_update_check = QPushButton("🔄 Cek Update")
        self.btn_update_check.setObjectName("brandVersion")
        self.btn_update_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update_check.setStyleSheet(
            "QPushButton { border: 1px solid palette(mid); border-radius: 4px; padding: 2px 7px; font-size: 11px; }"
            "QPushButton:hover { background-color: rgba(56, 189, 248, 0.15); border-color: #38BDF8; }"
        )
        self.btn_update_check.clicked.connect(self._check_for_updates)
        ft_layout.addWidget(self.btn_update_check)

        version_label = QLabel(f"Version {APP_VERSION}")
        version_label.setObjectName("brandVersion")
        ft_layout.addWidget(version_label)
        company_label = QLabel("PT. KEREAKTIF INDONESIA")
        company_label.setObjectName("brandVersion")
        ft_layout.addWidget(company_label)

        root_layout.addWidget(footer)

    def _setup_summary_tab(self):
        layout = QVBoxLayout(self.tab_summary)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Visual Hint Banner for right-click export
        hint_frame = QFrame()
        hint_frame.setObjectName("hintCard")
        h_layout = QHBoxLayout(hint_frame)
        h_layout.setContentsMargins(10, 5, 10, 5)
        h_layout.setSpacing(6)
        lbl_hint = QLabel(
            "<b>Tip:</b> Double-click a massive outage row to open its incident "
            "report. Right-click to export selected rows to Excel."
        )
        lbl_hint.setObjectName("hintText")
        h_layout.addWidget(lbl_hint)
        self.btn_incident_report = QPushButton("📋 Service Incident TT")
        self.btn_incident_report.setToolTip(
            "Select one massive outage row to create a copy-ready incident report."
        )
        self.btn_incident_report.clicked.connect(self._open_selected_incident_report)
        h_layout.addWidget(self.btn_incident_report)
        h_layout.addStretch()
        layout.addWidget(hint_frame)

        self.table_summary = QTableWidget()
        self.table_summary.setAlternatingRowColors(True)
        self.table_summary.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_summary.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_summary.customContextMenuRequested.connect(self._show_summary_context_menu)
        self.table_summary.cellDoubleClicked.connect(self._open_incident_report_for_row)
        self.table_summary.setToolTip(
            "Double-click a massive outage row to open its incident report, "
            "or right-click for more options."
        )
        self.table_summary.horizontalHeader().setStretchLastSection(True)
        self.table_summary.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_summary.verticalHeader().setDefaultSectionSize(30)
        self.table_summary.verticalHeader().setVisible(False)
        layout.addWidget(self.table_summary)

    def _setup_alarms_tab(self):
        layout = QVBoxLayout(self.tab_alarms)
        layout.setContentsMargins(6, 6, 6, 6)
        self.table_alarms = QTableWidget()
        self.table_alarms.setAlternatingRowColors(True)
        self.table_alarms.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_alarms.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_alarms.verticalHeader().setDefaultSectionSize(28)
        self.table_alarms.verticalHeader().setVisible(False)
        layout.addWidget(self.table_alarms)

    def _setup_sites_tab(self):
        layout = QVBoxLayout(self.tab_sites)
        layout.setContentsMargins(6, 6, 6, 6)
        self.table_sites = QTableWidget()
        self.table_sites.setAlternatingRowColors(True)
        self.table_sites.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_sites.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_sites.customContextMenuRequested.connect(self._show_sites_context_menu)
        self.table_sites.setToolTip(
            "Right-click to export impacted site data to Excel."
        )
        self.table_sites.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_sites.verticalHeader().setDefaultSectionSize(28)
        self.table_sites.verticalHeader().setVisible(False)
        layout.addWidget(self.table_sites)

    def _apply_theme(self, theme_name: str):
        self.current_theme_name = theme_name
        theme = THEMES_QSS[theme_name]
        if application := QApplication.instance():
            set_application_theme(theme_name, application)
        self.theme_selector.set_theme(theme_name)
        self.setStyleSheet("")

        # Update metric value colors
        palette_map = {
            "accent": theme["accent"],
            "signal": theme["signal"],
            "alert": theme["alert"],
        }
        for (card, color_key), val_lbl in zip(self.metric_cards, self.metric_vals):
            color = palette_map[color_key]
            val_lbl.setStyleSheet(f"color: {color};")

        if hasattr(self, "lbl_footer_spinner"):
            self.lbl_footer_spinner.setStyleSheet(f"color: {theme['accent']}; font-size: 13px; font-weight: bold;")
        self.recalculate()

    def _preset_today(self):
        self.date_start.setDate(QDate.currentDate())
        self.time_start.setTime(QTime(0, 0))
        self.date_end.setDate(QDate.currentDate())
        self.time_end.setTime(QTime.currentTime())
        self.recalculate()

    def _preset_last24h(self):
        now = datetime.now()
        yesterday = now - timedelta(hours=24)
        self.date_start.setDate(QDate(yesterday.year, yesterday.month, yesterday.day))
        self.time_start.setTime(QTime(yesterday.hour, yesterday.minute))
        self.date_end.setDate(QDate(now.year, now.month, now.day))
        self.time_end.setTime(QTime(now.hour, now.minute))
        self.recalculate()

    def _choose_alarm_file(self, vendor: str):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {vendor} Alarm Export",
            str(BASE_DIR),
            "Supported Alarm Files (*.zip *.xlsx *.xlsm *.xls *.csv *.txt *.dat *.bin);;All Files (*.*)",
        )
        if filename:
            if vendor == "ZTE":
                self.path_zte = filename
                self.edit_zte.setText(Path(filename).name)
            elif vendor == "Huawei":
                self.path_huawei = filename
                self.edit_hw.setText(Path(filename).name)
            else:
                self.path_fiberhome = filename
                self.edit_fh.setText(Path(filename).name)

    def _choose_master_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Site Management File",
            str(BASE_DIR),
            "Excel Workbooks (*.xlsx *.xls);;All Files (*.*)",
        )
        if filename:
            self.master_custom_path = filename
            self.edit_custom_master.setText(Path(filename).name)

    def _toggle_master_mode(self):
        is_custom = self.rb_master_custom.isChecked()
        self.master_mode = "custom" if is_custom else "default"
        self.edit_custom_master.setEnabled(is_custom)
        self.btn_browse_master.setEnabled(is_custom)

    def _selected_master_path(self) -> Path:
        if self.master_mode == "default":
            return DEFAULT_MASTER_PATH
        return Path(self.master_custom_path.strip())

    def _selected_time_range(self) -> tuple[datetime, datetime]:
        d1 = self.date_start.date()
        t1 = self.time_start.time()
        d2 = self.date_end.date()
        t2 = self.time_end.time()
        start = datetime(d1.year(), d1.month(), d1.day(), t1.hour(), t1.minute(), t1.second())
        end = datetime(d2.year(), d2.month(), d2.day(), t2.hour(), t2.minute(), t2.second())
        return start, end

    def _cycle_spinner(self):
        self._spinner_frame_idx = (self._spinner_frame_idx + 1) % len(SPINNER_FRAMES)
        frame = SPINNER_FRAMES[self._spinner_frame_idx]
        self.btn_run.setText(f"{frame} Analyzing...")
        self.lbl_progress_status.setText(f"{frame} {self._current_progress_msg}")
        self.lbl_footer_spinner.setText(frame)

    def _start_analysis_animation(self):
        self.btn_run.setEnabled(False)
        self.btn_recalc.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_reset_all.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.progress_deck.setVisible(True)
        self.footer_progress.setVisible(True)
        self.progress_bar.setValue(5)
        self.footer_progress.setValue(5)
        self.lbl_progress_pct.setText("5%")
        self._current_progress_msg = "Initializing correlation engine..."
        self.lbl_progress_status.setText(f"⠋ {self._current_progress_msg}")
        self.lbl_telemetry.setText("Initializing correlation engine...")
        self._spinner_frame_idx = 0
        self._spinner_timer.start()

    def _stop_analysis_animation(self, success: bool = True):
        self._spinner_timer.stop()
        self.btn_run.setEnabled(True)
        self.btn_run.setText("▶ Run Analysis")
        self.btn_recalc.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.btn_reset_all.setEnabled(True)
        self.btn_apply.setEnabled(True)
        self.progress_deck.setVisible(False)
        self.footer_progress.setVisible(False)
        self.lbl_footer_spinner.setText("●")

    def load_and_analyze(self):
        if self.worker is not None and self.worker.isRunning():
            return

        master_path = self._selected_master_path()
        vendor_paths = [
            ("ZTE", Path(self.path_zte)),
            ("Fiberhome", Path(self.path_fiberhome)),
            ("Huawei", Path(self.path_huawei)),
        ]
        vendor_paths = [(vendor, path) for vendor, path in vendor_paths if path.is_file()]

        if not master_path.is_file():
            QMessageBox.warning(self, "Site Management Missing", f"Site Management master file not found: {master_path}")
            return
        if not vendor_paths:
            QMessageBox.warning(self, "No Alarm Files", "Please select at least one alarm export file (ZTE, Fiberhome, or Huawei).")
            return

        self._start_analysis_animation()

        self.worker = AnalysisWorker(master_path, vendor_paths)
        self.worker.progress_stage.connect(self._on_worker_progress)
        self.worker.finished_success.connect(self._on_worker_success)
        self.worker.finished_error.connect(self._on_worker_error)
        self.worker.start()

    def reset_all_data(self):
        if self.worker is not None and self.worker.isRunning():
            return
        answer = QMessageBox.question(
            self,
            "Reset Massive Checker",
            "Remove all selected alarm files and clear the analysis, filters, "
            "and custom master selection?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.path_zte = ""
        self.path_fiberhome = ""
        self.path_huawei = ""
        self.edit_zte.clear()
        self.edit_fh.clear()
        self.edit_hw.clear()
        self.master_custom_path = ""
        self.edit_custom_master.clear()
        self.rb_master_default.setChecked(True)
        self.master_mode = "default"

        self.alarms.clear()
        self.imported.clear()
        self.summaries.clear()
        self.selected_vsats.clear()
        self.selected_alarm_types.clear()
        self.selected_alarm_names.clear()
        self.all_alarm_names.clear()
        self.menu_vsat.clear()
        self.menu_type.clear()
        self.btn_vsat_filter.setText("All VSAT Providers")
        self.btn_type_filter.setText("All Alarm Types")
        self.btn_alarm_name_filter.setText("All Alarms")
        self.spin_threshold.setValue(5)
        self.cb_spotbeam.setChecked(False)
        self._clear_tables()

        self.date_start.setDate(QDate.currentDate())
        self.time_start.setTime(QTime(0, 0))
        self.date_end.setDate(QDate.currentDate())
        self.time_end.setTime(QTime.currentTime())
        self.progress_bar.setValue(0)
        self.lbl_progress_pct.setText("0%")
        self.progress_deck.setVisible(False)
        self.footer_progress.setValue(0)
        self.footer_progress.setVisible(False)
        self.lbl_telemetry.setText(
            "Ready. Select alarm exports and run analysis."
        )
        self.tabs.setCurrentIndex(0)

    def closeEvent(self, event: Any) -> None:
        if self.worker is not None and self.worker.isRunning():
            self._close_pending = True
            self.hide()
            event.ignore()
            return
        super().closeEvent(event)

    def _on_worker_progress(self, msg: str, pct: int):
        self._current_progress_msg = msg
        frame = SPINNER_FRAMES[self._spinner_frame_idx]
        self.lbl_progress_status.setText(f"{frame} {msg}")
        self.lbl_progress_pct.setText(f"{pct}%")
        self.progress_bar.setValue(pct)
        self.footer_progress.setValue(pct)
        self.lbl_telemetry.setText(msg)

    def _on_worker_success(self, alarms: list[dict], imported: list[tuple[str, str, int, int]]):
        self.progress_bar.setValue(100)
        self.footer_progress.setValue(100)
        self.lbl_progress_pct.setText("100%")
        self._stop_analysis_animation(success=True)

        self.alarms = alarms
        self.imported = imported
        self._init_filter_menus()

        # Automatically adjust time range to match loaded alarm dates
        if self.alarms:
            min_t = min(a["Occurrence Time"] for a in self.alarms)
            max_t = max((a["Clear Time"] or a["Occurrence Time"]) for a in self.alarms)
            self.date_start.setDate(QDate(min_t.year, min_t.month, min_t.day))
            self.time_start.setTime(QTime(min_t.hour, min_t.minute))
            self.date_end.setDate(QDate(max_t.year, max_t.month, max_t.day))
            end_t = QTime(max_t.hour, max_t.minute)
            if max_t.second > 0 or max_t.microsecond > 0:
                end_t = end_t.addSecs(60)
            self.time_end.setTime(end_t)

        self.recalculate()

    def _on_worker_error(self, err_msg: str):
        self._stop_analysis_animation(success=False)
        self.lbl_telemetry.setText("Analysis failed.")
        QMessageBox.critical(self, "Data Processing Error", err_msg)

    def _init_filter_menus(self):
        self.all_alarm_names = sorted({alarm["Alarm Name"] for alarm in self.alarms})
        self.selected_alarm_names = _preferred_alarm_names(self.alarms)
        self.btn_alarm_name_filter.setText(f"Alarms ({len(self.selected_alarm_names)}/{len(self.all_alarm_names)})")

        providers = sorted({alarm["VSAT Provider"] or "Unknown" for alarm in self.alarms})
        self.selected_vsats = set(providers)
        self.menu_vsat.clear()
        act_all_vsat = self.menu_vsat.addAction("Select All")
        act_all_vsat.triggered.connect(self._select_all_vsats)
        act_clear_vsat = self.menu_vsat.addAction("Clear All")
        act_clear_vsat.triggered.connect(self._clear_all_vsats)
        self.menu_vsat.addSeparator()

        self.vsat_actions = {}
        for p in providers:
            act = QAction(p, self.menu_vsat)
            act.setCheckable(True)
            act.setChecked(True)
            act.triggered.connect(self._on_vsat_toggled)
            self.menu_vsat.addAction(act)
            self.vsat_actions[p] = act
        self._update_vsat_button_text()

        types = sorted({alarm["Alarm Type"] or "Unknown" for alarm in self.alarms})
        self.selected_alarm_types = set(types)
        self.menu_type.clear()
        act_all_type = self.menu_type.addAction("Select All")
        act_all_type.triggered.connect(self._select_all_types)
        act_clear_type = self.menu_type.addAction("Clear All")
        act_clear_type.triggered.connect(self._clear_all_types)
        self.menu_type.addSeparator()

        self.type_actions = {}
        for t in types:
            act = QAction(t, self.menu_type)
            act.setCheckable(True)
            act.setChecked(True)
            act.triggered.connect(self._on_type_toggled)
            self.menu_type.addAction(act)
            self.type_actions[t] = act
        self._update_type_button_text()

    def _select_all_vsats(self):
        for act in self.vsat_actions.values():
            act.setChecked(True)
        self.selected_vsats = set(self.vsat_actions.keys())
        self._update_vsat_button_text()
        self.recalculate()

    def _clear_all_vsats(self):
        for act in self.vsat_actions.values():
            act.setChecked(False)
        self.selected_vsats = set()
        self._update_vsat_button_text()
        self.recalculate()

    def _on_vsat_toggled(self):
        self.selected_vsats = {p for p, act in self.vsat_actions.items() if act.isChecked()}
        self._update_vsat_button_text()
        self.recalculate()

    def _update_vsat_button_text(self):
        count = len(self.selected_vsats)
        total = len(self.vsat_actions)
        self.btn_vsat_filter.setText(f"All VSATs ({total})" if count == total else f"VSATs ({count}/{total})")

    def _select_all_types(self):
        for act in self.type_actions.values():
            act.setChecked(True)
        self.selected_alarm_types = set(self.type_actions.keys())
        self._update_type_button_text()
        self.recalculate()

    def _clear_all_types(self):
        for act in self.type_actions.values():
            act.setChecked(False)
        self.selected_alarm_types = set()
        self._update_type_button_text()
        self.recalculate()

    def _on_type_toggled(self):
        self.selected_alarm_types = {t for t, act in self.type_actions.items() if act.isChecked()}
        self._update_type_button_text()
        self.recalculate()

    def _update_type_button_text(self):
        count = len(self.selected_alarm_types)
        total = len(self.type_actions)
        self.btn_type_filter.setText(f"All Types ({total})" if count == total else f"Types ({count}/{total})")

    def _open_alarm_name_dialog(self):
        if not self.all_alarm_names:
            return
        theme = THEMES_QSS[self.current_theme_name]
        dialog = AlarmNameFilterDialog(self, self.all_alarm_names, self.selected_alarm_names, theme)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.selected_alarm_names = dialog.get_selected()
            self.btn_alarm_name_filter.setText(f"Alarms ({len(self.selected_alarm_names)}/{len(self.all_alarm_names)})")
            self.recalculate()

    def recalculate(self):
        if not self.alarms:
            return
        min_sites = self.spin_threshold.value()

        if not self.selected_alarm_names or not self.selected_vsats or not self.selected_alarm_types:
            self.lbl_telemetry.setText("Please select at least one VSAT, Alarm Type, and Alarm Name to compute results.")
            self._clear_tables()
            return

        try:
            range_start, range_end = self._selected_time_range()
            if range_start >= range_end:
                raise ValueError("Start time must be earlier than end time.")
        except ValueError as err:
            QMessageBox.warning(self, "Invalid Time Range", str(err))
            return

        scoped = [
            a for a in self.alarms
            if (a["VSAT Provider"] or "Unknown") in self.selected_vsats
            and (a["Alarm Type"] or "Unknown") in self.selected_alarm_types
            and _alarm_overlaps_range(a, range_start, range_end)
        ]
        self.summaries = summarize_providers(
            scoped,
            self.selected_alarm_names,
            minimum_sites=min_sites,
            group_by_spotbeam=self.cb_spotbeam.isChecked(),
            range_start=range_start,
            range_end=range_end,
        )

        filtered_alarms = [
            a for a in scoped
            if a["Alarm Name"] in self.selected_alarm_names
            and _alarm_overlaps_range(a, range_start, range_end)
        ]
        range_sites = {a["Site ID"] for a in filtered_alarms}
        massive_groups = [s for s in self.summaries if s["Massive Down"]]
        largest_peak = max((s["Peak Simultaneous Sites"] for s in self.summaries), default=0)

        # Update KPI values
        self.metric_vals[0].setText(f"{len(range_sites):,}")
        self.metric_vals[1].setText(f"{largest_peak:,}")
        self.metric_vals[2].setText(f"{len(massive_groups):,}")

        self._fill_summary_table()
        self._fill_alarms_table(filtered_alarms)
        self._fill_sites_table(massive_groups)

        alarm_total = sum(item[2] for item in self.imported)
        mapped_total = sum(item[3] for item in self.imported)
        vendors = ", ".join(item[0] for item in self.imported)
        self.lbl_telemetry.setText(
            f"Sources: {vendors} · {len(filtered_alarms):,} alarms in range · "
            f"{mapped_total:,}/{alarm_total:,} mapped sites · {len(self.selected_alarm_names)} alarms · "
            f"{len(self.selected_vsats)} VSATs · {len(self.selected_alarm_types)} types · "
            f"{_format_datetime(range_start)} to {_format_datetime(range_end)} · "
            f"Master: {self._selected_master_path().name}"
        )

    def _clear_tables(self):
        self.table_summary.setRowCount(0)
        self.table_alarms.setRowCount(0)
        self.table_sites.setRowCount(0)
        for v in self.metric_vals:
            v.setText("-")
        self.summaries = []

    def _fill_summary_table(self):
        theme = THEMES_QSS[self.current_theme_name]
        headers = [
            "VSAT Provider", "Spotbeam", "Current Down Sites",
            "Peak Simultaneous Sites", "Peak Time", "Massive Outage"
        ]
        self.table_summary.setColumnCount(len(headers))
        self.table_summary.setHorizontalHeaderLabels(headers)
        self.table_summary.setRowCount(len(self.summaries))

        massive_bg = QColor(theme["massive_bg"])
        massive_fg = QColor(theme["massive_text"])

        for row, s in enumerate(self.summaries):
            is_massive = s["Massive Down"]
            vals = [
                s["VSAT Provider"],
                s["Spotbeam"],
                s["Current Down Sites"],
                s["Peak Simultaneous Sites"],
                _format_datetime(s["Peak Time"]),
                "YES" if is_massive else "NO",
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem()
                if col in (2, 3):
                    # Store as int for proper numeric sorting
                    item.setData(Qt.ItemDataRole.EditRole, int(val))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                else:
                    item.setData(Qt.ItemDataRole.DisplayRole, str(val))
                    if col in (0, 1):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    else:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if is_massive:
                    item.setBackground(massive_bg)
                    item.setForeground(massive_fg)
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                self.table_summary.setItem(row, col, item)

        self.table_summary.setSortingEnabled(True)
        self.table_summary.resizeColumnsToContents()

    def _fill_alarms_table(self, alarms: list[dict]):
        self.table_alarms.setSortingEnabled(False)
        self.table_alarms.setColumnCount(len(NORMALIZED_COLUMNS))
        self.table_alarms.setHorizontalHeaderLabels(NORMALIZED_COLUMNS)
        self.table_alarms.setRowCount(len(alarms))

        for row, a in enumerate(alarms):
            for col, key in enumerate(NORMALIZED_COLUMNS):
                val = a.get(key, "")
                if isinstance(val, datetime):
                    val = _format_datetime(val)
                item = QTableWidgetItem(str(val or ""))
                self.table_alarms.setItem(row, col, item)

        self.table_alarms.setSortingEnabled(True)
        self.table_alarms.resizeColumnsToContents()

    def _fill_sites_table(self, massive_groups: list[dict]):
        self.table_sites.setSortingEnabled(False)
        headers = ["VSAT Provider", "Spotbeam", "Peak Time", "Site ID", "Site Name", "Paket", "Area", "Status BAPL", "Duration"]
        self.table_sites.setColumnCount(len(headers))
        self.table_sites.setHorizontalHeaderLabels(headers)

        rows_data = [
            [
                row.get("VSAT Provider", ""),
                row.get("_summary_spotbeam", row.get("Spotbeam", "")),
                _format_datetime(row.get("_peak_time")),
                row.get("Site ID", ""),
                row.get("Site Name", ""),
                row.get("Paket", ""),
                row.get("Area", ""),
                row.get("Status BAPL", ""),
                row.get("Duration", ""),
            ]
            for row in _selected_site_report_rows(self.alarms, massive_groups)
        ]

        self.table_sites.setRowCount(len(rows_data))
        for row, vals in enumerate(rows_data):
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                self.table_sites.setItem(row, col, item)

        self.table_sites.setSortingEnabled(True)
        self.table_sites.resizeColumnsToContents()

    def _show_summary_context_menu(self, pos):
        item = self.table_summary.itemAt(pos)
        if item is not None:
            row = item.row()
            if not self.table_summary.item(row, 0).isSelected():
                self.table_summary.clearSelection()
                self.table_summary.selectRow(row)

        menu = QMenu(self)
        if item is not None:
            summary = self._summary_for_table_row(item.row())
            if summary and summary["Massive Down"]:
                act_copy_report = menu.addAction("📋 Lihat / Copy Incident Report...")
                act_copy_report.triggered.connect(
                    lambda checked=False, incident=summary: self._show_incident_report(incident)
                )
                menu.addSeparator()

        has_sel = self.table_summary.selectionModel().hasSelection()
        if has_sel:
            count = len({idx.row() for idx in self.table_summary.selectionModel().selectedRows()})
            act_export_sel = menu.addAction(f"📄 Export Selected ({count} Row/Provider) to Excel...")
            act_export_sel.triggered.connect(self.export_selected_summary_rows)
            menu.addSeparator()

        act_export_all = menu.addAction("📊 Export All Analysis Results to Excel...")
        act_export_all.triggered.connect(self.export_report)
        menu.exec(self.table_summary.viewport().mapToGlobal(pos))

    def _summary_for_table_row(self, row: int) -> dict | None:
        provider_item = self.table_summary.item(row, 0)
        spotbeam_item = self.table_summary.item(row, 1)
        peak_time_item = self.table_summary.item(row, 4)
        if not provider_item or not spotbeam_item or not peak_time_item:
            return None

        row_key = (provider_item.text(), spotbeam_item.text(), peak_time_item.text())
        return next(
            (
                summary for summary in self.summaries
                if (
                    summary["VSAT Provider"],
                    summary["Spotbeam"],
                    _format_datetime(summary.get("Peak Time")),
                ) == row_key
            ),
            None,
        )

    def _open_incident_report_for_row(self, row: int, _column: int) -> None:
        summary = self._summary_for_table_row(row)
        if summary and summary["Massive Down"]:
            self._show_incident_report(summary)

    def _show_incident_report(self, summary: dict) -> None:
        try:
            range_start, range_end = self._selected_time_range()
        except ValueError:
            QMessageBox.warning(self, "Invalid Time Range", "Please verify start and end times.")
            return

        selected_alarms, selected_summaries = _report_data_for_selection(
            self.alarms,
            [summary],
            self.selected_alarm_names,
            self.selected_vsats,
            self.selected_alarm_types,
            range_start,
            range_end,
            group_by_spotbeam=self.cb_spotbeam.isChecked(),
        )
        site_rows = _selected_site_report_rows(selected_alarms, selected_summaries)
        impacted_site_ids = {row.get("Site ID") for row in site_rows}
        peak_time = summary.get("Peak Time")
        if peak_time:
            window_start = peak_time - timedelta(minutes=45)
            window_end = peak_time + timedelta(minutes=15)
            incident_alarms = [
                alarm for alarm in selected_alarms
                if alarm.get("Site ID") in impacted_site_ids
                and alarm.get("Occurrence Time") is not None
                and window_start <= alarm["Occurrence Time"] <= window_end
            ]
        else:
            incident_alarms = [
                alarm for alarm in selected_alarms
                if alarm.get("Site ID") in impacted_site_ids
            ]
        report_text = _executive_summary_text(incident_alarms, site_rows, selected_summaries)

        dialog = QDialog(self)
        dialog.setWindowTitle("Service Incident TT Report")
        dialog.resize(720, 760)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(
            "Copy the selected massive outage report below and paste it where needed."
        ))

        report_editor = QPlainTextEdit()
        report_editor.setReadOnly(True)
        report_editor.setPlainText(report_text)
        layout.addWidget(report_editor)

        buttons = QHBoxLayout()
        copy_button = QPushButton("📋 Copy Report")
        copy_status = QLabel("")

        def copy_report() -> None:
            QApplication.clipboard().setText(report_editor.toPlainText())
            copy_status.setText("Report copied.")

        copy_button.clicked.connect(copy_report)
        buttons.addWidget(copy_button)
        buttons.addWidget(copy_status)
        buttons.addStretch()

        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        dialog.exec()

    def _open_selected_incident_report(self) -> None:
        selected_rows = sorted({
            index.row()
            for index in self.table_summary.selectionModel().selectedRows()
        })
        if len(selected_rows) != 1:
            QMessageBox.information(
                self,
                "Select a Massive Outage",
                "Select exactly one massive outage row, then click Service Incident TT.",
            )
            return

        summary = self._summary_for_table_row(selected_rows[0])
        if not summary or not summary["Massive Down"]:
            QMessageBox.information(
                self,
                "Not a Massive Outage",
                "The selected row is not a massive outage.",
            )
            return
        self._show_incident_report(summary)

    def _show_sites_context_menu(self, pos):
        menu = QMenu(self)
        massive_summaries = [s for s in self.summaries if s["Massive Down"]]
        if massive_summaries:
            count = sum(len(s.get("Sites at Peak", [])) for s in massive_summaries)
            act_export_sites = menu.addAction(f"📄 Export All Sites at Peak ({count} Sites) to Excel...")
            act_export_sites.triggered.connect(self._export_sites_at_peak)
            menu.addSeparator()
        act_export_all = menu.addAction("📊 Export All Analysis Results to Excel...")
        act_export_all.triggered.connect(self.export_report)
        menu.exec(self.table_sites.viewport().mapToGlobal(pos))

    def _export_sites_at_peak(self):
        """Export all massive outage sites from Sites at Peak tab."""
        massive_summaries = [s for s in self.summaries if s["Massive Down"]]
        if not massive_summaries:
            QMessageBox.information(self, "No Massive Outages", "No massive outage incidents to export.")
            return
        try:
            start, end = self._selected_time_range()
        except ValueError:
            QMessageBox.warning(self, "Invalid Time Range", "Please verify start and end times.")
            return

        selected_alarms, selected_summaries = _report_data_for_selection(
            self.alarms,
            massive_summaries,
            self.selected_alarm_names,
            self.selected_vsats,
            self.selected_alarm_types,
            start,
            end,
            group_by_spotbeam=self.cb_spotbeam.isChecked(),
        )
        all_site_rows = _selected_site_report_rows(selected_alarms, selected_summaries)
        suggested_name = _suggested_selected_export_filename(selected_summaries, all_site_rows, start)

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Sites at Peak to Excel",
            str(BASE_DIR / suggested_name),
            "Excel Workbook (*.xlsx)",
        )
        if not path:
            return
        try:
            save_selected_site_report(path, selected_alarms, selected_summaries)
            self._prompt_open_exported_file(path)
        except Exception as error:
            QMessageBox.critical(self, "Export Failed", str(error))

    def _prompt_open_exported_file(self, path: str | Path):
        path_obj = Path(path).resolve()
        self.lbl_telemetry.setText(f"Exported: {path_obj.name}")

        msg = QMessageBox(self)
        msg.setWindowTitle("Export Completed")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(f"Report exported successfully!\n\nFilename:\n{path_obj.name}")
        msg.setInformativeText(f"Location:\n{path_obj}\n\nWould you like to open it now?")

        btn_open = msg.addButton("Open Excel File", QMessageBox.ButtonRole.AcceptRole)
        btn_folder = msg.addButton("Open Folder", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_open)

        msg.exec()

        if msg.clickedButton() == btn_open:
            try:
                if sys.platform == "win32":
                    os.startfile(str(path_obj))
                else:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path_obj)))
            except Exception as err:
                QMessageBox.warning(self, "Error", f"Unable to open file:\n{err}")
        elif msg.clickedButton() == btn_folder:
            try:
                if sys.platform == "win32":
                    subprocess.Popen(f'explorer /select,"{path_obj}"')
                else:
                    os.startfile(str(path_obj.parent))
            except Exception as err:
                QMessageBox.warning(self, "Error", f"Unable to open folder:\n{err}")

    def export_selected_summary_rows(self):
        selected_rows = sorted({idx.row() for idx in self.table_summary.selectionModel().selectedRows()})
        if not selected_rows:
            if not self.summaries:
                QMessageBox.information(self, "Select Rows", "Please select one or more summary rows first.")
                return
            selected_rows = list(range(len(self.summaries)))

        selected_keys = {
            (
                self.table_summary.item(row, 0).text(),
                self.table_summary.item(row, 1).text(),
                self.table_summary.item(row, 4).text(),
            )
            for row in selected_rows
            if self.table_summary.item(row, 0)
            and self.table_summary.item(row, 1)
            and self.table_summary.item(row, 4)
        }
        try:
            start, end = self._selected_time_range()
        except ValueError:
            QMessageBox.warning(self, "Invalid Time Range", "Please verify start and end times.")
            return

        selected_alarms, selected_summaries = _report_data_for_selection(
            self.alarms,
            self.summaries,
            self.selected_alarm_names,
            self.selected_vsats,
            self.selected_alarm_types,
            start,
            end,
            selected_summary_keys=selected_keys,
            group_by_spotbeam=self.cb_spotbeam.isChecked(),
        )
        all_site_rows = _selected_site_report_rows(selected_alarms, selected_summaries)
        suggested_name = _suggested_selected_export_filename(selected_summaries, all_site_rows, start)

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Selected Sites to Excel",
            str(BASE_DIR / suggested_name),
            "Excel Workbook (*.xlsx)",
        )
        if not path:
            return
        try:
            save_selected_site_report(path, selected_alarms, selected_summaries)
            self._prompt_open_exported_file(path)
        except Exception as error:
            QMessageBox.critical(self, "Export Failed", str(error))

    def export_report(self):
        if not self.summaries:
            QMessageBox.information(self, "No Results", "Please run analysis first.")
            return
        try:
            start, end = self._selected_time_range()
        except ValueError:
            QMessageBox.warning(self, "Invalid Time Range", "Please verify start and end times.")
            return

        filtered_alarms = [
            a for a in self.alarms
            if a["Alarm Name"] in self.selected_alarm_names
            and (a["VSAT Provider"] or "Unknown") in self.selected_vsats
            and (a["Alarm Type"] or "Unknown") in self.selected_alarm_types
            and _alarm_overlaps_range(a, start, end)
        ]
        start_str = start.strftime("%Y%m%d_%H%M")
        end_str = end.strftime("%Y%m%d_%H%M")
        suggested_name = f"NOC Alarm Report {start_str} to {end_str}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save NOC Alarm Report (Occurrence Range)",
            str(BASE_DIR / suggested_name),
            "Excel Workbook (*.xlsx)",
        )
        if not path:
            return
        try:
            save_report(path, filtered_alarms, self.summaries)
            self._prompt_open_exported_file(path)
        except Exception as error:
            QMessageBox.critical(self, "Export Failed", str(error))

    def _check_for_updates(self) -> None:
        """Check for updates on GitHub Releases."""
        self.btn_update_check.setText("⏳ Memeriksa...")
        self.btn_update_check.setEnabled(False)

        worker = CheckUpdateWorker(parent=self)

        def on_found(info: dict) -> None:
            tag = info.get("tag_name", "")
            self.btn_update_check.setText(f"🔥 Update {tag}!")
            self.btn_update_check.setEnabled(True)
            self.btn_update_check.setStyleSheet(
                "QPushButton { background-color: #0284C7; color: white; font-weight: bold; padding: 2px 10px; border-radius: 4px; border: none; }"
                "QPushButton:hover { background-color: #0369A1; }"
            )
            dlg = UpdateDialog(info, self)
            dlg.exec()

        def on_up_to_date(_info: dict) -> None:
            self.btn_update_check.setText("🔄 Cek Update")
            self.btn_update_check.setEnabled(True)
            QMessageBox.information(
                self,
                "Aplikasi Terkini",
                f"Aplikasi {APP_NAME} sudah menggunakan versi terbaru (v{APP_VERSION}).",
            )

        def on_no_release(repo: str) -> None:
            self.btn_update_check.setText("🔄 Cek Update")
            self.btn_update_check.setEnabled(True)
            QMessageBox.information(
                self,
                "Belum Ada Rilis",
                f"Belum ada rilis pada repository GitHub:\n{repo}",
            )

        def on_failed(err: str) -> None:
            self.btn_update_check.setText("🔄 Cek Update")
            self.btn_update_check.setEnabled(True)
            msg = QMessageBox(self)
            msg.setWindowTitle("Pemeriksaan Update")
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setText(f"Tidak dapat memeriksa update:\n\n{err}")
            msg.setInformativeText(f"Target repository: {get_github_repo()}")
            btn_cfg = msg.addButton("Ubah Repository...", QMessageBox.ButtonRole.ActionRole)
            msg.addButton("Tutup", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            if msg.clickedButton() == btn_cfg:
                configure_github_repo_dialog(self)

        worker.update_found.connect(on_found)
        worker.up_to_date.connect(on_up_to_date)
        worker.no_release.connect(on_no_release)
        worker.check_failed.connect(on_failed)
        self._manual_updater_worker = worker
        worker.start()


class AppSelectionDialog(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} | Select an application")
        self.resize(620, 500)
        self.selection: str | None = None
        application = QApplication.instance()
        self.current_theme_name = (
            application.property("nocTheme") if application else None
        ) or system_theme_name(application)
        self.theme_selector = ThemeSelector(self.current_theme_name)
        self.theme_selector.themeChanged.connect(self._apply_theme)
        if application is not None:
            set_application_theme(self.current_theme_name, application)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 18)
        layout.setSpacing(13)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(14)
        brand_row.addWidget(NocLogoMark(64))
        brand_text = QVBoxLayout()
        brand_text.setSpacing(3)
        title = QLabel(APP_NAME)
        title.setObjectName("brandTitle")
        brand_text.addWidget(title)
        subtitle = QLabel("Operations workspace")
        subtitle.setObjectName("brandSubtitle")
        brand_text.addWidget(subtitle)
        brand_row.addLayout(brand_text, 1)
        brand_row.addWidget(self.theme_selector)
        layout.addLayout(brand_row)

        instruction = QLabel("Choose an application to open")
        instruction.setObjectName("brandSubtitle")
        layout.addWidget(instruction)

        massive_button = QPushButton("Check Massive Outages")
        massive_button.setObjectName("appChoice")
        massive_button.setMinimumHeight(52)
        massive_button.setToolTip("Analyze alarms and affected sites.")
        massive_button.clicked.connect(lambda: self._select("massive"))
        layout.addWidget(massive_button)

        cctv_button = QPushButton("Extract Capture CCTV")
        cctv_button.setObjectName("appChoice")
        cctv_button.setMinimumHeight(52)
        cctv_button.setToolTip("Process CCTV captures and export to an Excel template.")
        cctv_button.clicked.connect(lambda: self._select("cctv"))
        layout.addWidget(cctv_button)

        self.choice_shadow_effects: list[QGraphicsDropShadowEffect] = []
        for button in (massive_button, cctv_button):
            shadow = QGraphicsDropShadowEffect(button)
            shadow.setBlurRadius(18)
            shadow.setOffset(0, 4)
            self.choice_shadow_effects.append(shadow)
            button.setGraphicsEffect(shadow)

        settings = _display_settings()
        display_card = QFrame()
        display_card.setObjectName("card")
        display_layout = QGridLayout(display_card)
        display_layout.setContentsMargins(14, 12, 14, 12)
        display_layout.setHorizontalSpacing(12)
        display_layout.setVerticalSpacing(7)

        scale_label = QLabel("Display scale")
        self.scale_combo = QComboBox()
        for scale_percent in SCALE_OPTIONS:
            label = f"{scale_percent}%"
            if scale_percent == DEFAULT_SCALE_PERCENT:
                label += " (Recommended)"
            self.scale_combo.addItem(label, scale_percent)
        self.scale_combo.setCurrentIndex(
            self.scale_combo.findData(_saved_scale_percent(settings))
        )
        self.scale_combo.setToolTip(
            "Set the interface scale used by NOC Tools. Windows display settings stay unchanged."
        )
        resolution_label = QLabel("App resolution")
        self.resolution_combo = QComboBox()
        for resolution in WINDOW_RESOLUTIONS:
            width, height = WINDOW_RESOLUTIONS[resolution]
            label = f"{width} × {height}"
            if resolution == DEFAULT_RESOLUTION:
                label += " (Recommended)"
            self.resolution_combo.addItem(label, resolution)
        self.resolution_combo.setCurrentIndex(
            self.resolution_combo.findData(_saved_resolution(settings))
        )
        self.resolution_combo.setToolTip(
            "Set the NOC Tools window size. The window is limited to the current screen."
        )
        display_layout.addWidget(scale_label, 0, 0)
        display_layout.addWidget(resolution_label, 0, 1)
        display_layout.addWidget(self.scale_combo, 1, 0)
        display_layout.addWidget(self.resolution_combo, 1, 1)
        display_layout.setColumnStretch(0, 1)
        display_layout.setColumnStretch(1, 1)

        settings_note = QLabel(
            "These options affect NOC Tools only. Changing scale restarts the selected app once."
        )
        settings_note.setObjectName("brandSubtitle")
        settings_note.setWordWrap(True)
        display_layout.addWidget(settings_note, 2, 0, 1, 2)
        layout.addWidget(display_card)

        self.application_choice_buttons = (massive_button, cctv_button)

        layout.addStretch(1)
        footer = QHBoxLayout()
        footer_line = QFrame()
        footer_line.setFrameShape(QFrame.Shape.HLine)
        footer_line.setFrameShadow(QFrame.Shadow.Plain)
        footer_line.setStyleSheet("color: palette(mid);")
        layout.addWidget(footer_line)
        footer_text = QLabel("PT. KEREAKTIF INDONESIA")
        footer_text.setObjectName("brandVersion")
        footer.addWidget(footer_text)
        footer.addStretch()

        self.btn_update = QPushButton("🔄 Cek Update")
        self.btn_update.setObjectName("brandVersion")
        self.btn_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update.setStyleSheet(
            "QPushButton { border: 1px solid palette(mid); border-radius: 4px; padding: 2px 8px; font-size: 11px; }"
            "QPushButton:hover { background-color: rgba(56, 189, 248, 0.15); border-color: #38BDF8; }"
        )
        self.btn_update.clicked.connect(self._manual_check_update)
        footer.addWidget(self.btn_update)

        footer_version = QLabel(f"Version {APP_VERSION}")
        footer_version.setObjectName("brandVersion")
        footer.addWidget(footer_version)
        layout.addLayout(footer)
        self._apply_theme(self.current_theme_name)

        # Silent background update check
        self._cached_release: dict | None = None
        self._start_background_update_check()

    def _apply_theme(self, theme_name: str) -> None:
        self.current_theme_name = theme_name
        application = QApplication.instance()
        if application is not None:
            set_application_theme(theme_name, application)
        self.theme_selector.set_theme(theme_name)
        shadow_color = QColor(
            "#030712" if theme_name == DARK_THEME else "#64748B"
        )
        shadow_color.setAlpha(90)
        for shadow in self.choice_shadow_effects:
            shadow.setColor(shadow_color)

    def _select(self, selection: str) -> None:
        self.selection = selection
        self.accept()

    def _start_background_update_check(self) -> None:
        """Silently checks for updates in the background on startup."""
        self._bg_worker = CheckUpdateWorker(parent=self)
        self._bg_worker.update_found.connect(self._on_bg_update_found)
        self._bg_worker.start()

    def _on_bg_update_found(self, release_info: dict) -> None:
        self._cached_release = release_info
        tag = release_info.get("tag_name", "")
        self.btn_update.setText(f"🔥 Update {tag}!")
        self.btn_update.setStyleSheet(
            "QPushButton { background-color: #0284C7; color: white; font-weight: bold; padding: 2px 10px; border-radius: 4px; border: none; font-size: 11px; }"
            "QPushButton:hover { background-color: #0369A1; }"
        )

    def _manual_check_update(self) -> None:
        if self._cached_release:
            dlg = UpdateDialog(self._cached_release, self)
            dlg.exec()
            return

        self.btn_update.setText("⏳ Memeriksa...")
        self.btn_update.setEnabled(False)
        self._manual_worker = CheckUpdateWorker(parent=self)

        def on_found(info: dict) -> None:
            self._cached_release = info
            tag = info.get("tag_name", "")
            self.btn_update.setText(f"🔥 Update {tag}!")
            self.btn_update.setEnabled(True)
            self.btn_update.setStyleSheet(
                "QPushButton { background-color: #0284C7; color: white; font-weight: bold; padding: 2px 10px; border-radius: 4px; border: none; font-size: 11px; }"
                "QPushButton:hover { background-color: #0369A1; }"
            )
            dlg = UpdateDialog(info, self)
            dlg.exec()

        def on_up_to_date(_info: dict) -> None:
            self.btn_update.setText("🔄 Cek Update")
            self.btn_update.setEnabled(True)
            QMessageBox.information(
                self,
                "Aplikasi Terkini",
                f"Aplikasi {APP_NAME} sudah versi terbaru (v{APP_VERSION}).",
            )

        def on_no_release(repo: str) -> None:
            self.btn_update.setText("🔄 Cek Update")
            self.btn_update.setEnabled(True)
            QMessageBox.information(
                self,
                "Belum Ada Rilis",
                f"Belum ada rilis pada repository GitHub:\n{repo}",
            )

        def on_failed(err: str) -> None:
            self.btn_update.setText("🔄 Cek Update")
            self.btn_update.setEnabled(True)
            msg = QMessageBox(self)
            msg.setWindowTitle("Pemeriksaan Update")
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setText(f"Tidak dapat memeriksa update:\n\n{err}")
            msg.setInformativeText(f"Target repository: {get_github_repo()}")
            btn_cfg = msg.addButton("Ubah Repository...", QMessageBox.ButtonRole.ActionRole)
            msg.addButton("Tutup", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            if msg.clickedButton() == btn_cfg:
                configure_github_repo_dialog(self)

        self._manual_worker.update_found.connect(on_found)
        self._manual_worker.up_to_date.connect(on_up_to_date)
        self._manual_worker.no_release.connect(on_no_release)
        self._manual_worker.check_failed.connect(on_failed)
        self._manual_worker.start()


def _relaunch_with_scale(
    selection: str,
    scale_percent: int,
    resolution: str,
    theme_name: str,
    system_dpi: int,
) -> None:
    environment = os.environ.copy()
    environment["QT_SCALE_FACTOR"] = f"{_qt_scale_factor(scale_percent, system_dpi):.6f}"
    environment["NOC_TOOLS_RESOLUTION"] = resolution
    environment["NOC_TOOLS_THEME"] = theme_name
    environment["NOC_TOOLS_LAUNCH_APP"] = selection

    if getattr(sys, "frozen", False):
        command = [sys.executable]
    else:
        entry_point = Path(sys.argv[0])
        if not entry_point.is_absolute():
            entry_point = BASE_DIR / entry_point
        command = [sys.executable, str(entry_point.resolve())]
    subprocess.Popen(command, cwd=BASE_DIR, env=environment)


def main() -> int:
    settings = _display_settings()
    starting_scale = _saved_scale_percent(settings)
    system_dpi = _system_dpi()
    os.environ["QT_SCALE_FACTOR"] = (
        f"{_qt_scale_factor(starting_scale, system_dpi):.6f}"
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    theme_name = os.environ.pop("NOC_TOOLS_THEME", "")
    if not theme_name:
        theme_name = str(
            settings.value("appearance/theme", system_theme_name(app))
        )
    if theme_name not in THEMES:
        theme_name = system_theme_name(app)
    set_application_theme(theme_name, app)
    app.setQuitOnLastWindowClosed(False)

    def launch_selected_app(
        selection: str,
        resolution: str,
        scale_percent: int,
    ) -> bool:
        if selection == "massive":
            window = MassiveSiteDownApp()
        elif selection == "cctv":
            window = CCTVReportMainWindow()
        else:
            return False

        apply_standard_window_chrome(window)
        _apply_window_resolution(window, resolution, scale_percent)
        return_filter.set_active_window(window)
        window.showMaximized()
        return True

    def show_launcher() -> bool:
        while True:
            selection_dialog = AppSelectionDialog()
            if selection_dialog.exec() != QDialog.DialogCode.Accepted:
                return False

            selection = selection_dialog.selection or ""
            selected_scale = int(selection_dialog.scale_combo.currentData())
            resolution = str(selection_dialog.resolution_combo.currentData())
            selected_theme = str(app.property("nocTheme") or theme_name)

            settings.setValue("display/scalePercent", selected_scale)
            settings.setValue("display/resolution", resolution)
            settings.setValue("appearance/theme", selected_theme)

            if selected_scale != starting_scale:
                try:
                    _relaunch_with_scale(
                        selection,
                        selected_scale,
                        resolution,
                        selected_theme,
                        system_dpi,
                    )
                except OSError as error:
                    QMessageBox.critical(
                        selection_dialog,
                        "Unable to Apply Display Scale",
                        "NOC Tools could not restart to apply the selected "
                        f"scale.\n\n{error}",
                    )
                    continue
                return False

            return launch_selected_app(
                selection,
                resolution,
                selected_scale,
            )

    return_filter = _LauncherReturnFilter(
        lambda _window: show_launcher() or app.quit(),
        app,
    )
    resumed_selection = os.environ.pop("NOC_TOOLS_LAUNCH_APP", "")
    if resumed_selection in ("massive", "cctv"):
        resumed_resolution = os.environ.pop(
            "NOC_TOOLS_RESOLUTION",
            _saved_resolution(settings),
        )
        if resumed_resolution not in WINDOW_RESOLUTIONS:
            resumed_resolution = _saved_resolution(settings)
        if not launch_selected_app(
            resumed_selection,
            resumed_resolution,
            starting_scale,
        ):
            return 1
    elif not show_launcher():
        return 0

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
