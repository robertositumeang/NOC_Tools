from __future__ import annotations

import ctypes
import os

from PyQt6.QtCore import QSettings


SCALE_OPTIONS = (100, 125, 150, 175)
DEFAULT_SCALE_PERCENT = 100


def display_settings() -> QSettings:
    return QSettings("PT. KEREAKTIF INDONESIA", "NOC Tools")


def saved_scale_percent(settings: QSettings | None = None) -> int:
    settings = settings or display_settings()
    try:
        scale_percent = int(
            settings.value("display/scalePercent", DEFAULT_SCALE_PERCENT)
        )
    except (TypeError, ValueError):
        return DEFAULT_SCALE_PERCENT
    return (
        scale_percent
        if scale_percent in SCALE_OPTIONS
        else DEFAULT_SCALE_PERCENT
    )


def system_dpi() -> int:
    if os.name == "nt":
        try:
            dpi = int(ctypes.windll.user32.GetDpiForSystem())
        except (AttributeError, OSError, TypeError, ValueError):
            return 96
        return dpi if dpi > 0 else 96
    return 96


def qt_scale_factor(scale_percent: int, dpi: int) -> float:
    if scale_percent <= 0 or dpi <= 0:
        raise ValueError("Scale percentage and system DPI must be positive.")
    return scale_percent * 96 / (100 * dpi)


def configure_qt_scale() -> None:
    os.environ["QT_SCALE_FACTOR"] = (
        f"{qt_scale_factor(saved_scale_percent(), system_dpi()):.6f}"
    )
