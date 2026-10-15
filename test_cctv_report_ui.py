from __future__ import annotations

from PyQt6.QtWidgets import QApplication

from CCTV_Report.cctv_report_app import MainWindow
from noc_brand import DARK_THEME, LIGHT_THEME, set_application_theme


def test_cctv_theme_toggle_restyles_canvas_without_removing_workflow():
    application = QApplication.instance() or QApplication([])
    previous_theme = application.property("nocTheme")
    previous_stylesheet = application.styleSheet()
    previous_icon = application.windowIcon()
    set_application_theme(DARK_THEME, application)
    window = MainWindow()
    try:
        assert window.theme_selector is not None
        assert window.main_tabs.count() == 2
        assert window.process_button.objectName() == "accentBtn"
        assert window.export_button.objectName() == "accentBtn"

        window.theme_selector.light_button.click()
        assert window.current_theme_name == LIGHT_THEME
        assert application.property("nocTheme") == LIGHT_THEME
        assert "#F2F6FC" in application.styleSheet()
        for canvas in window.calibration_canvases.values():
            assert canvas._canvas_background.name() == "#eaf1f9"
            assert canvas._canvas_text.name() == "#52677f"

        window.theme_selector.dark_button.click()
        assert window.current_theme_name == DARK_THEME
        assert application.property("nocTheme") == DARK_THEME
        assert "#091526" in application.styleSheet()
        for canvas in window.calibration_canvases.values():
            assert canvas._canvas_background.name() == "#172b48"
            assert canvas._canvas_text.name() == "#a8b9cf"
    finally:
        window.close()
        application.removeEventFilter(window)
        application.setStyleSheet(previous_stylesheet)
        application.setProperty("nocTheme", previous_theme)
        application.setWindowIcon(previous_icon)
