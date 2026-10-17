from __future__ import annotations

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QToolButton,
    QWidget,
)


APP_NAME = "NOC Tools"
APP_VERSION = "1.0.7"
DARK_THEME = "Midnight Neon (Dark)"
LIGHT_THEME = "Apple Modern (Light)"


def paint_network_background(
    painter: QPainter,
    bounds: QRectF | QRect,
    is_dark: bool = True,
    opacity: float = 0.50,
) -> None:
    """Renders the signature NOC network motif:
    - Subtle ambient radial glow
    - Smooth curved tech waves
    - Latitude/longitude globe arcs
    - Constellation nodes with glowing pulse rings and connection lines
    Adjusts colors for dark/light themes and applies the requested opacity factor.
    """
    if isinstance(bounds, QRect):
        bounds = QRectF(bounds)
    if bounds.width() <= 0 or bounds.height() <= 0:
        return

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # 1. Subtle radial ambient glow
    glow_center = QPointF(bounds.width() * 0.70, bounds.height() * 0.85)
    glow_radius = max(bounds.width(), bounds.height()) * 0.75
    glow = QRadialGradient(glow_center, glow_radius)
    if is_dark:
        glow.setColorAt(0.0, QColor(0, 115, 255, int(90 * opacity)))
        glow.setColorAt(0.45, QColor(0, 60, 180, int(40 * opacity)))
        glow.setColorAt(1.0, QColor(0, 20, 60, 0))
    else:
        glow.setColorAt(0.0, QColor(18, 111, 232, int(60 * opacity)))
        glow.setColorAt(0.45, QColor(56, 189, 248, int(25 * opacity)))
        glow.setColorAt(1.0, QColor(240, 245, 252, 0))
    painter.fillRect(bounds, glow)

    # Secondary glow top-left
    glow2 = QRadialGradient(
        QPointF(bounds.width() * 0.15, bounds.height() * 0.20),
        bounds.width() * 0.5,
    )
    if is_dark:
        glow2.setColorAt(0.0, QColor(42, 168, 242, int(45 * opacity)))
        glow2.setColorAt(1.0, QColor(9, 21, 38, 0))
    else:
        glow2.setColorAt(0.0, QColor(18, 111, 232, int(25 * opacity)))
        glow2.setColorAt(1.0, QColor(242, 246, 252, 0))
    painter.fillRect(bounds, glow2)

    # 2. Smooth tech waves (Bezier curves)
    wave_color = (
        QColor(18, 111, 232, int(80 * opacity))
        if is_dark
        else QColor(37, 99, 235, int(50 * opacity))
    )
    painter.setPen(QPen(wave_color, 1.0))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for offset in (0.12, 0.28, 0.44):
        wave = QPainterPath()
        wave.moveTo(bounds.width() * offset, bounds.height() * 0.70)
        wave.cubicTo(
            bounds.width() * 0.42,
            bounds.height() * 0.60,
            bounds.width() * 0.68,
            bounds.height() * 0.44,
            bounds.width() * 1.02,
            bounds.height() * (0.18 + offset * 0.25),
        )
        painter.drawPath(wave)

    # 3. Globe latitude & longitude arcs
    globe_rect = QRectF(
        -bounds.width() * 0.10,
        bounds.height() * 0.55,
        bounds.width() * 1.25,
        bounds.height() * 1.05,
    )
    main_arc_color = (
        QColor(0, 140, 255, int(130 * opacity))
        if is_dark
        else QColor(18, 111, 232, int(90 * opacity))
    )
    sub_arc_color = (
        QColor(0, 115, 255, int(65 * opacity))
        if is_dark
        else QColor(18, 111, 232, int(45 * opacity))
    )

    painter.setPen(QPen(main_arc_color, 1.2))
    painter.drawArc(globe_rect, 0, 180 * 16)

    painter.setPen(QPen(sub_arc_color, 0.8))
    for idx in range(1, 5):
        inset_x = globe_rect.width() * idx * 0.075
        inset_y = globe_rect.height() * idx * 0.07
        painter.drawArc(
            globe_rect.adjusted(inset_x, inset_y, -inset_x, -inset_y),
            0,
            180 * 16,
        )

    # Longitudinal meridian curves
    for span in (0.44, 0.86):
        painter.drawArc(
            QRectF(
                globe_rect.center().x() - globe_rect.width() * (span / 2),
                globe_rect.top(),
                globe_rect.width() * span,
                globe_rect.height(),
            ),
            0,
            180 * 16,
        )

    # 4. Constellation nodes & connecting lines
    net_line_color = (
        QColor(0, 160, 255, int(110 * opacity))
        if is_dark
        else QColor(18, 111, 232, int(75 * opacity))
    )
    painter.setPen(QPen(net_line_color, 0.9))

    nodes = (
        (0.08, 0.84),
        (0.22, 0.73),
        (0.36, 0.78),
        (0.50, 0.68),
        (0.66, 0.76),
        (0.82, 0.65),
        (0.95, 0.80),
    )
    points = [
        QPointF(bounds.width() * x, bounds.height() * y)
        for x, y in nodes
    ]

    for p1, p2 in zip(points, points[1:]):
        painter.drawLine(p1, p2)

    # Draw node circles & luminous pulses
    for idx, pt in enumerate(points):
        painter.setPen(Qt.PenStyle.NoPen)
        node_color = (
            QColor(56, 189, 248, int(240 * opacity))
            if is_dark
            else QColor(14, 116, 204, int(220 * opacity))
        )
        painter.setBrush(node_color)
        r = 3.2 if idx in (1, 3, 5) else 2.0
        painter.drawEllipse(pt, r, r)

        # Pulse halo ring on accent nodes
        if idx in (1, 3, 5):
            halo_color = (
                QColor(56, 189, 248, int(45 * opacity))
                if is_dark
                else QColor(14, 116, 204, int(35 * opacity))
            )
            painter.setBrush(halo_color)
            painter.drawEllipse(pt, 8.5, 8.5)

    painter.restore()

THEMES = {
    DARK_THEME: {
        "app_bg": "#091526",
        "card_bg": "#10213A",
        "card_alt": "#172B48",
        "border": "#294363",
        "text": "#EEF5FF",
        "muted": "#A8B9CF",
        "accent": "#2AA8F2",
        "accent_hover": "#58BDF8",
        "secondary": "#4C83E6",
        "signal": "#F4B94E",
        "alert": "#F4778C",
        "table_row_alt": "#142743",
        "massive_bg": "#402333",
        "massive_text": "#FFB0BD",
    },
    LIGHT_THEME: {
        "app_bg": "#F2F6FC",
        "card_bg": "#FFFFFF",
        "card_alt": "#EAF1F9",
        "border": "#D2DFEE",
        "text": "#15263B",
        "muted": "#52677F",
        "accent": "#126FE8",
        "accent_hover": "#075CC7",
        "secondary": "#3F67C8",
        "signal": "#9B6500",
        "alert": "#B42345",
        "table_row_alt": "#F3F7FC",
        "massive_bg": "#FCE8ED",
        "massive_text": "#8F1732",
    },
}


def system_theme_name(application: QApplication | None = None) -> str:
    app = application or QApplication.instance()
    if app is not None:
        scheme = app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return DARK_THEME
        if scheme == Qt.ColorScheme.Light:
            return LIGHT_THEME
        background = app.palette().color(QPalette.ColorRole.Window)
        if background.lightness() < 128:
            return DARK_THEME
    return LIGHT_THEME


def palette_for(theme_name: str) -> dict[str, str]:
    return THEMES[theme_name]


def apply_standard_window_chrome(window: QMainWindow) -> None:
    window.setWindowFlags(
        Qt.WindowType.Window
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowSystemMenuHint
        | Qt.WindowType.WindowMinimizeButtonHint
        | Qt.WindowType.WindowMaximizeButtonHint
        | Qt.WindowType.WindowCloseButtonHint
    )


def theme_stylesheet(theme_name: str) -> str:
    theme = THEMES[theme_name]
    accent_text = "#0F172A" if theme_name == DARK_THEME else "#FFFFFF"
    selected_bg = theme["secondary"] if theme_name == DARK_THEME else theme["accent"]
    return f"""
        QMainWindow, QDialog, QWidget#centralWidget {{
            background: {theme["app_bg"]};
            color: {theme["text"]};
            font-family: "Segoe UI";
            font-size: 12px;
        }}
        QWidget {{ color: {theme["text"]}; }}
        QFrame#card, QGroupBox {{
            background: {theme["card_bg"]};
            border: 1px solid {theme["border"]};
            border-radius: 12px;
        }}
        QFrame#headerCard, QWidget#brandHeader {{
            background: {theme["card_bg"]};
            border-bottom: 1px solid {theme["border"]};
        }}
        QFrame#cctvHeader {{
            background: {theme["card_bg"]};
            border: 1px solid {theme["border"]};
            border-radius: 12px;
        }}
        QWidget#busyBanner {{
            background: {theme["card_alt"]};
            border: 1px solid {theme["border"]};
            border-radius: 7px;
        }}
        QFrame#footerCard, QWidget#brandFooter {{
            background: {theme["card_bg"]};
            border-top: 1px solid {theme["border"]};
        }}
        QGroupBox {{
            margin-top: 10px;
            padding: 10px 8px 8px;
            font-weight: 600;
        }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
        QLabel {{ background: transparent; }}
        QLabel#headerTitle, QLabel#brandTitle {{
            color: {theme["text"]}; font-size: 16px; font-weight: 700;
        }}
        QLabel#brandSubtitle, QLabel#footerText, QLabel#themeTag {{
            color: {theme["muted"]}; font-size: 11px;
        }}
        QLabel#brandVersion {{
            color: {theme["muted"]}; font-size: 10px; font-weight: 600;
        }}
        QLabel#sectionTitle {{ color: {theme["secondary"]}; font-weight: 700; }}
        QLineEdit, QSpinBox, QDateEdit, QTimeEdit, QComboBox, QPlainTextEdit {{
            background: {theme["card_bg"]};
            color: {theme["text"]};
            border: 1px solid {theme["border"]};
            border-radius: 6px;
            padding: 6px 8px;
            selection-background-color: {selected_bg};
            selection-color: #FFFFFF;
        }}
        QLineEdit:focus, QSpinBox:focus, QDateEdit:focus, QTimeEdit:focus,
        QComboBox:focus, QPlainTextEdit:focus {{
            border: 1px solid {theme["accent"]};
        }}
        QPushButton {{
            background: {theme["card_alt"]};
            color: {theme["text"]};
            border: 1px solid {theme["border"]};
            border-radius: 7px;
            padding: 7px 12px;
            font-weight: 600;
        }}
        QPushButton:hover {{ border-color: {theme["accent"]}; background: {theme["card_bg"]}; }}
        QPushButton:pressed {{ padding-top: 8px; padding-bottom: 6px; }}
        QPushButton#accentBtn {{
            background: {theme["accent"]}; color: {accent_text};
            border: none; font-weight: 700;
        }}
        QPushButton#accentBtn:hover {{ background: {theme["accent_hover"]}; }}
        QPushButton#appChoice {{
            background: {theme["card_bg"]};
            text-align: left;
            padding: 16px 18px;
            border: 1px solid {theme["border"]};
            border-radius: 14px;
        }}
        QPushButton#appChoice:hover {{
            background: {theme["card_alt"]};
            border-color: {theme["accent"]};
        }}
        QPushButton#appChoice QLabel#appChoiceIndex {{
            color: {theme["accent"]}; font-size: 10px; font-weight: 700;
        }}
        QPushButton#appChoice QLabel#appChoiceTitle {{
            color: {theme["text"]}; font-size: 19px; font-weight: 700;
        }}
        QPushButton#appChoice QLabel#appChoiceDescription {{
            color: {theme["muted"]}; font-size: 11px;
        }}
        QPushButton#appChoice QLabel#appChoiceAction {{
            color: {theme["accent"]}; font-size: 11px; font-weight: 700;
        }}
        QToolButton#themeToggleButton {{
            background: {theme["card_alt"]}; color: {theme["muted"]};
            border: 1px solid {theme["border"]}; border-radius: 7px;
            min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
            font-size: 17px;
        }}
        QToolButton#themeToggleButton:checked {{
            background: {theme["accent"]}; color: {accent_text};
            border-color: {theme["accent"]};
        }}
        QTabWidget::pane {{
            background: {theme["card_bg"]}; border: 1px solid {theme["border"]};
            border-radius: 8px;
        }}
        QTabBar::tab {{
            background: {theme["card_alt"]}; color: {theme["muted"]};
            padding: 8px 16px; margin-right: 3px; border-top-left-radius: 6px;
            border-top-right-radius: 6px; font-weight: 600;
        }}
        QTabBar::tab:selected {{ background: {selected_bg}; color: #FFFFFF; }}
        QTableWidget, QTableView {{
            background: {theme["card_bg"]}; alternate-background-color: {theme["table_row_alt"]};
            color: {theme["text"]}; gridline-color: {theme["border"]}; border: none;
            selection-background-color: {selected_bg}; selection-color: #FFFFFF;
        }}
        QHeaderView::section {{
            background: {theme["card_alt"]}; color: {theme["muted"]};
            border: 1px solid {theme["border"]}; padding: 6px 8px; font-weight: 700;
        }}
        QScrollBar:vertical {{ background: {theme["card_bg"]}; width: 10px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {theme["border"]}; border-radius: 5px; min-height: 22px; }}
        QScrollBar::handle:vertical:hover {{ background: {theme["accent"]}; }}
        QScrollBar:horizontal {{ background: {theme["card_bg"]}; height: 10px; margin: 0; }}
        QScrollBar::handle:horizontal {{ background: {theme["border"]}; border-radius: 5px; min-width: 22px; }}
        QCheckBox, QRadioButton {{ spacing: 6px; }}
        QProgressBar {{
            background: {theme["card_alt"]}; border: 1px solid {theme["border"]};
            border-radius: 4px; text-align: center;
        }}
        QProgressBar::chunk {{ background: {theme["accent"]}; border-radius: 3px; }}
        QMenu, QComboBox QAbstractItemView {{
            background: {theme["card_bg"]}; color: {theme["text"]};
            border: 1px solid {theme["border"]}; selection-background-color: {selected_bg};
        }}
        QToolTip {{
            background: {theme["card_bg"]}; color: {theme["text"]};
            border: 1px solid {theme["accent"]}; padding: 5px;
        }}
    """


def set_application_theme(
    theme_name: str,
    application: QApplication | None = None,
) -> None:
    app = application or QApplication.instance()
    if app is None:
        raise RuntimeError("A QApplication instance is required to apply a theme.")
    app.setProperty("nocTheme", theme_name)
    app.setStyleSheet(theme_stylesheet(theme_name))
    app.setWindowIcon(app_icon(theme_name))
    for widget in app.allWidgets():
        widget.update()


class ThemeSelector(QWidget):
    themeChanged = pyqtSignal(str)

    def __init__(self, theme_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.light_button = QToolButton(self)
        self.light_button.setText("☀")
        self.light_button.setToolTip("Light theme")
        self.light_button.setAccessibleName("Light theme")
        self.light_button.setObjectName("themeToggleButton")
        self.light_button.setCheckable(True)
        self.light_button.setAutoExclusive(True)

        self.dark_button = QToolButton(self)
        self.dark_button.setText("☾")
        self.dark_button.setToolTip("Dark theme")
        self.dark_button.setAccessibleName("Dark theme")
        self.dark_button.setObjectName("themeToggleButton")
        self.dark_button.setCheckable(True)
        self.dark_button.setAutoExclusive(True)

        layout.addWidget(self.light_button)
        layout.addWidget(self.dark_button)
        self.light_button.clicked.connect(
            lambda: self.themeChanged.emit(LIGHT_THEME)
        )
        self.dark_button.clicked.connect(
            lambda: self.themeChanged.emit(DARK_THEME)
        )
        self.set_theme(theme_name)

    def set_theme(self, theme_name: str) -> None:
        self.light_button.setChecked(theme_name == LIGHT_THEME)
        self.dark_button.setChecked(theme_name == DARK_THEME)


class NocLogoMark(QWidget):
    def __init__(self, size: int = 56, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        left, top = (self.width() - side) / 2, (self.height() - side) / 2
        polygons = (
            ((0.08, 0.76), (0.29, 0.25), (0.51, 0.25), (0.30, 0.76)),
            ((0.46, 0.76), (0.67, 0.25), (0.90, 0.25), (0.69, 0.76)),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        for points, color in zip(polygons, ("#168BFF", "#20D5FF")):
            polygon = QPolygonF(
                [QPointF(left + side * x, top + side * y) for x, y in points]
            )
            painter.setBrush(QColor(color))
            painter.drawPolygon(polygon)
        painter.end()


def app_icon(theme_name: str) -> QIcon:
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.GlobalColor.transparent)
    mark = NocLogoMark(120)
    mark.resize(120, 120)
    mark.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    mark.setProperty("themeName", theme_name)
    if application := QApplication.instance():
        old_theme = application.property("nocTheme")
        application.setProperty("nocTheme", theme_name)
        mark.ensurePolished()
        mark.render(
            pixmap,
            pixmap.rect().topLeft(),
            flags=QWidget.RenderFlag.DrawChildren,
        )
        application.setProperty("nocTheme", old_theme)
    return QIcon(pixmap)
