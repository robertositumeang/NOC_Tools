from __future__ import annotations

import sys
from math import cos, radians, sin
from typing import Callable

from PyQt6.QtCore import (
    QEventLoop,
    QObject,
    QPointF,
    QRectF,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from startup_config import configure_qt_scale


class StartupSplash(QWidget):
    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setFixedSize(440, 196)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAccessibleName("NOC Tools startup")
        self.setAccessibleDescription("Loading NOC Tools")
        self._rotation = 0
        self._loading_dots = 0
        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._advance_animation)
        self._timer.start()

    def center_on_screen(self, application: QApplication) -> None:
        screen = application.primaryScreen()
        if screen is not None:
            self.move(screen.availableGeometry().center() - self.rect().center())

    def _advance_animation(self) -> None:
        self._rotation = (self._rotation + 12) % 360
        if self._rotation % 120 == 0:
            self._loading_dots = (self._loading_dots + 1) % 4
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        panel = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setPen(QPen(QColor("#293750"), 1))
        painter.setBrush(QColor("#0F172A"))
        painter.drawRoundedRect(panel, 18, 18)

        painter.setPen(QColor("#F8FAFC"))
        painter.setFont(QFont("Segoe UI", 18, QFont.Weight.DemiBold))
        painter.drawText(
            QRectF(32, 34, 340, 32),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "NOC Tools",
        )

        painter.setPen(QColor("#AAB2C8"))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(
            QRectF(34, 72, 350, 24),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "Preparing your workspace",
        )

        center = QPointF(371, 111)
        radius = 17
        for index in range(12):
            angle = self._rotation + index * 30
            point_angle = radians(angle)
            point = QPointF(
                center.x() + cos(point_angle) * radius,
                center.y() + sin(point_angle) * radius,
            )
            alpha = 70 + (index * 15)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(34, 211, 238, alpha))
            painter.drawEllipse(point, 2.2, 2.2)

        painter.setPen(QColor("#22D3EE"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        painter.drawText(
            QRectF(34, 126, 360, 22),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"Loading{'.' * self._loading_dots}",
        )

    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)


class _StartupSplashDismissal(QObject):
    def __init__(
        self,
        splash: StartupSplash,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._splash = splash
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setInterval(50)
        self._dismiss_timer.timeout.connect(self._check_visible_window)

    def start(self) -> None:
        self._dismiss_timer.start()

    def _check_visible_window(self) -> None:
        application = QApplication.instance()
        if application is None:
            return
        if any(
            window is not self._splash and window.isVisible()
            for window in application.topLevelWidgets()
        ):
            self._dismiss_timer.stop()
            self._splash.close()


class _DesktopAppImportWorker(QThread):
    loaded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            from desktop_app import main as desktop_app_main
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")
            return
        self.loaded.emit(desktop_app_main)


def main() -> int:
    configure_qt_scale()
    application = QApplication(sys.argv)
    application.setApplicationName("NOC Tools")
    application.setQuitOnLastWindowClosed(False)

    splash = StartupSplash()
    splash.center_on_screen(application)
    splash.show()
    application.processEvents()

    loader = _DesktopAppImportWorker()
    import_loop = QEventLoop()
    load_result: dict[str, Callable[[], int] | str] = {}

    def set_loaded(desktop_app_main: Callable[[], int]) -> None:
        load_result["main"] = desktop_app_main
        import_loop.quit()

    def set_import_error(message: str) -> None:
        load_result["error"] = message
        import_loop.quit()

    loader.loaded.connect(set_loaded)
    loader.failed.connect(set_import_error)
    loader.start()
    import_loop.exec()
    loader.wait()

    if "error" in load_result:
        splash.close()
        QMessageBox.critical(
            None,
            "NOC Tools Startup Failed",
            f"Unable to load the application:\n\n{load_result['error']}",
        )
        return 1

    desktop_app_main = load_result.get("main")
    if not callable(desktop_app_main):
        splash.close()
        QMessageBox.critical(
            None,
            "NOC Tools Startup Failed",
            "Application startup did not provide a launch function.",
        )
        return 1
    dismissal_filter = _StartupSplashDismissal(splash, application)
    dismissal_filter.start()
    try:
        return desktop_app_main()
    except Exception as error:
        splash.close()
        QMessageBox.critical(
            None,
            "NOC Tools Startup Failed",
            f"{type(error).__name__}: {error}",
        )
        return 1
    finally:
        dismissal_filter._dismiss_timer.stop()
        splash.close()


if __name__ == "__main__":
    sys.exit(main())
