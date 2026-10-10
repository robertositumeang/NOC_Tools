from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPalette, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QToolButton,
    QWidget,
)


APP_NAME = "NOC Tools"
APP_VERSION = "1.0.0"
DARK_THEME = "Midnight Neon (Dark)"
LIGHT_THEME = "Apple Modern (Light)"

THEMES = {
    DARK_THEME: {
        "app_bg": "#0F172A",
        "card_bg": "#161D30",
        "card_alt": "#202A43",
        "border": "#303B58",
        "text": "#EDE9FE",
        "muted": "#AAB2C8",
        "accent": "#22D3EE",
        "accent_hover": "#67E8F9",
        "secondary": "#7C3AED",
        "signal": "#A78BFA",
        "alert": "#FB7185",
        "table_row_alt": "#1B263D",
        "massive_bg": "#3B1D35",
        "massive_text": "#FDA4AF",
    },
    LIGHT_THEME: {
        "app_bg": "#F5F5F7",
        "card_bg": "#FFFFFF",
        "card_alt": "#EBEDF1",
        "border": "#D6D8DE",
        "text": "#1D1D1F",
        "muted": "#60646C",
        "accent": "#007AFF",
        "accent_hover": "#0066D6",
        "secondary": "#7C3AED",
        "signal": "#6D5AE6",
        "alert": "#C6284B",
        "table_row_alt": "#F0F1F4",
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
            border-radius: 10px;
        }}
        QFrame#headerCard, QWidget#brandHeader {{
            background: {theme["card_bg"]};
            border-bottom: 1px solid {theme["border"]};
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
            background: {theme["card_bg"]}; text-align: left;
            padding: 12px 14px; border-radius: 9px;
        }}
        QPushButton#appChoice:hover {{ background: {theme["card_alt"]}; border-color: {theme["accent"]}; }}
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
        QTableWidget {{
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
        theme = THEMES.get(
            QApplication.instance().property("nocTheme")
            if QApplication.instance() else "",
            THEMES[LIGHT_THEME],
        )
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        inset = side * 0.05
        panel = self.rect().adjusted(round(inset), round(inset), -round(inset), -round(inset))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme["card_alt"]))
        painter.drawRoundedRect(panel, side * 0.24, side * 0.24)

        path = QPainterPath()
        path.moveTo(side * 0.29, side * 0.68)
        path.lineTo(side * 0.29, side * 0.31)
        path.lineTo(side * 0.68, side * 0.69)
        path.lineTo(side * 0.68, side * 0.31)
        painter.setPen(QColor(theme["accent"]))
        pen = painter.pen()
        pen.setWidthF(max(2.0, side * 0.075))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme["secondary"]))
        painter.drawEllipse(round(side * 0.61), round(side * 0.23), round(side * 0.16), round(side * 0.16))
        painter.setBrush(QColor(theme["accent"]))
        painter.drawEllipse(round(side * 0.22), round(side * 0.61), round(side * 0.16), round(side * 0.16))


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
