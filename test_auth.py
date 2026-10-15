"""Unit tests for administrator-managed NOC Tools authentication."""
from __future__ import annotations

import json
import os

import pytest

import auth
import auth_admin
from auth import verify_credentials


@pytest.fixture
def credential_store(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    salt = os.urandom(16)
    password_hash = auth._derive_credential_hash("StrongTestPassword!2026", salt)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "users": [
                    {
                        "username": "operator",
                        "display_name": "NOC Operator",
                        "salt": salt.hex(),
                        "password_hash": password_hash.hex(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(auth, "_CREDENTIALS_FILE", path)
    return path


def test_valid_credentials_from_administrator_store(credential_store):
    assert verify_credentials("operator", "StrongTestPassword!2026") == (
        True,
        "NOC Operator",
    )


def test_password_and_username_are_case_sensitive(credential_store):
    assert verify_credentials("operator", "strongtestpassword!2026") == (False, "")
    assert verify_credentials("Operator", "StrongTestPassword!2026") == (False, "")


def test_unknown_user_and_invalid_password_fail(credential_store):
    assert verify_credentials("missing-user", "StrongTestPassword!2026") == (False, "")
    assert verify_credentials("operator", "WrongPassword!2026") == (False, "")


def test_empty_credentials_fail_without_reading_store(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "_CREDENTIALS_FILE", tmp_path / "missing.json")
    assert verify_credentials("", "") == (False, "")
    assert verify_credentials("operator", "   ") == (False, "")


def test_missing_credential_store_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "_CREDENTIALS_FILE", tmp_path / "missing.json")
    assert verify_credentials("operator", "StrongTestPassword!2026") == (False, "")


def test_frozen_app_uses_worker_even_when_adjacent_credential_store_exists(
    tmp_path, monkeypatch
):
    portable_dir = tmp_path / "portable"
    portable_dir.mkdir()
    portable_store = portable_dir / "users.json"
    portable_store.write_text("legacy sidecar", encoding="utf-8")
    monkeypatch.setattr(auth.sys, "frozen", True, raising=False)
    monkeypatch.setattr(auth.sys, "executable", str(portable_dir / "NOC Tools.exe"))
    calls = []
    monkeypatch.setattr(
        auth,
        "operator_login",
        lambda username, password: (
            calls.append((username, password)) or (True, "Cloudflare Operator")
        ),
    )

    assert verify_credentials("operator", "PortablePassword!2026") == (
        True,
        "Cloudflare Operator",
    )
    assert calls == [("operator", "PortablePassword!2026")]


def test_frozen_app_does_not_read_local_credential_store(tmp_path, monkeypatch):
    executable = tmp_path / "portable" / "NOC Tools.exe"
    executable.parent.mkdir()
    monkeypatch.setattr(auth.sys, "frozen", True, raising=False)
    monkeypatch.setattr(auth.sys, "executable", str(executable))
    monkeypatch.setattr(
        auth,
        "_read_credential_records",
        lambda *_args: (_ for _ in ()).throw(AssertionError("local store was read")),
    )
    monkeypatch.setattr(
        auth,
        "operator_login",
        lambda username, password: (True, "Cloudflare Operator"),
    )

    assert verify_credentials("operator", "StrongTestPassword!2026") == (
        True,
        "Cloudflare Operator",
    )


def test_malformed_credential_store_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(auth, "_CREDENTIALS_FILE", path)
    assert verify_credentials("operator", "StrongTestPassword!2026") == (False, "")


def test_credential_record_with_invalid_hash_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "users": [
                    {
                        "username": "operator",
                        "display_name": "NOC Operator",
                        "salt": "00",
                        "password_hash": "00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(auth, "_CREDENTIALS_FILE", path)
    assert verify_credentials("operator", "StrongTestPassword!2026") == (False, "")


def test_admin_can_add_reset_and_remove_an_account(tmp_path, monkeypatch):
    store_path = tmp_path / "users.json"
    monkeypatch.setattr(auth, "_CREDENTIALS_FILE", store_path)
    monkeypatch.setattr(auth_admin, "_apply_windows_acl", lambda path, *, is_directory: None)

    auth_admin.set_user(
        "operator",
        "NOC Operator",
        "StrongTestPassword!2026",
        store_path=store_path,
    )
    assert verify_credentials("operator", "StrongTestPassword!2026") == (
        True,
        "NOC Operator",
    )
    assert "StrongTestPassword!2026" not in store_path.read_text(encoding="utf-8")

    auth_admin.set_user(
        "OPERATOR",
        "Shift Operator",
        "ReplacementPassword!2026",
        store_path=store_path,
    )
    assert verify_credentials("operator", "StrongTestPassword!2026") == (False, "")
    assert verify_credentials("OPERATOR", "ReplacementPassword!2026") == (
        True,
        "Shift Operator",
    )
    assert auth_admin.remove_user("operator", store_path=store_path) is True
    assert verify_credentials("OPERATOR", "ReplacementPassword!2026") == (False, "")
    assert auth_admin.remove_user("operator", store_path=store_path) is False


def test_relaunch_tokens_are_not_part_of_authentication_api():
    assert not hasattr(auth, "make_session_token")
    assert not hasattr(auth, "verify_session_token")


def test_login_dialog_license_expired_locks_form(monkeypatch):
    from PyQt6.QtWidgets import QApplication
    from auth import LoginDialog

    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "auth.check_active_license",
        lambda: (False, "Lisensi telah kedaluwarsa", 0, "2026-03-01"),
    )
    dialog = LoginDialog()
    assert dialog._is_lic_valid is False
    assert "LICENSE EXPIRED" in dialog.lbl_lic_badge.text()
    assert dialog.lic_card.isHidden() is False
    assert dialog.txt_username.isEnabled() is False
    assert dialog.txt_password.isEnabled() is False
    assert dialog.btn_login.isEnabled() is False
    assert not dialog.btn_activate_lic.isHidden()


def test_login_dialog_license_active_unlocks_form(monkeypatch):
    from PyQt6.QtWidgets import QApplication
    from auth import LoginDialog

    _ = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "auth.check_active_license",
        lambda: (True, "Lisensi Aktif", 30, "2026-11-10"),
    )
    dialog = LoginDialog()
    assert dialog._is_lic_valid is True
    assert dialog.lic_card.isHidden() is True
    assert dialog.txt_username.isEnabled() is True
    assert dialog.txt_password.isEnabled() is True
    assert dialog.btn_login.isEnabled() is True
    assert dialog.btn_activate_lic.isHidden()


def test_login_dialog_matches_split_noc_design_and_footer_placement(monkeypatch):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QWidget
    from auth import LoginDialog

    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "auth.check_active_license",
        lambda: (True, "Lisensi Aktif", 30, "2026-11-10"),
    )
    dialog = LoginDialog()
    dialog.show()
    application.processEvents()

    login_panel = dialog.findChild(QFrame, "loginShell")
    brand_panel = dialog.findChild(QFrame, "brandPanel")
    form_panel = dialog.findChild(QFrame, "formPanel")
    assert dialog.size().width() == 960
    assert dialog.size().height() == 590
    assert not dialog.windowIcon().isNull()
    assert login_panel is not None
    assert brand_panel is not None
    assert form_panel is not None
    assert dialog.findChild(QWidget, "brandMark") is not None
    assert brand_panel.width() > form_panel.width()

    labels = {label.objectName(): label for label in dialog.findChildren(QLabel)}
    assert labels["footerBadge"].text() == "Admin : PT. KEREAKTIF INDONESIA"
    assert labels["brandFootnote"].text() == "OPERATIONS  /  MONITORING  /  RESPONSE"
    assert labels["footerBadge"].alignment() & Qt.AlignmentFlag.AlignRight
    assert labels["brandFootnote"].alignment() & Qt.AlignmentFlag.AlignRight
    all_text = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "CONTROL DESK" not in all_text
    assert "Satu akses terpusat" not in all_text
    assert "Additional Tools" in all_text
    assert "DASHBOARD" in all_text
    assert "CCTV" in all_text
    assert "CAPTURE MODEM" in all_text
    assert "VPN Manager" not in all_text
    assert "Ping" not in all_text
    assert "Traceroute" not in all_text
    assert "Device Tools" not in all_text
    assert "Terminal" not in all_text
    assert labels["brandFootnote"].parentWidget() is form_panel
    assert labels["footerBadge"].parentWidget() is form_panel
    assert labels["brandFootnote"].geometry().top() > labels["footerBadge"].geometry().top()


def test_login_dialog_animates_while_credentials_are_checked(monkeypatch):
    import threading

    from PyQt6.QtCore import QEventLoop, QTimer
    from PyQt6.QtWidgets import QApplication, QDialog
    from auth import LoginDialog

    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "auth.check_active_license",
        lambda: (True, "Lisensi Aktif", 30, "2026-11-10"),
    )
    verification_started = threading.Event()
    continue_verification = threading.Event()

    def delayed_verification(username, password):
        verification_started.set()
        continue_verification.wait(timeout=3)
        return True, "NOC Operator"

    monkeypatch.setattr("auth.verify_credentials", delayed_verification)
    dialog = LoginDialog()
    dialog.txt_username.setText("operator")
    dialog.txt_password.setText("test-password")
    dialog._handle_login()

    assert verification_started.wait(timeout=1)
    assert dialog.login_spinner._timer.isActive()
    assert dialog.lbl_loading.isHidden() is False
    assert dialog.btn_login.isEnabled() is False
    assert dialog.txt_username.isEnabled() is False

    event_loop = QEventLoop()
    spinner_angles = []
    QTimer.singleShot(80, lambda: spinner_angles.append(dialog.login_spinner.angle))
    dialog.finished.connect(event_loop.quit)
    QTimer.singleShot(1500, event_loop.quit)
    QTimer.singleShot(120, continue_verification.set)
    event_loop.exec()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert spinner_angles and spinner_angles[0] != 0
    assert dialog.authenticated_user == "NOC Operator"
    assert dialog.login_spinner.isHidden()
    application.processEvents()


def test_login_dialog_branding_and_password_visibility_toggle(monkeypatch):
    from PyQt6.QtWidgets import QApplication, QLabel, QLineEdit
    from auth import LoginDialog

    _ = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "auth.check_active_license",
        lambda: (True, "Lisensi Aktif", 30, "2026-11-10"),
    )
    dialog = LoginDialog()
    labels = [label.text() for label in dialog.findChildren(QLabel)]

    assert "PT. KEREAKTIF INDONESIA" in labels
    assert "Admin : PT. KEREAKTIF INDONESIA" in labels
    assert all("RESTRICTED AREA" not in label for label in labels)
    assert dialog.btn_toggle_password.isCheckable()
    assert dialog.btn_toggle_password.text() == ""
    assert not dialog.btn_toggle_password.icon().isNull()
    assert dialog.txt_password.echoMode() == QLineEdit.EchoMode.Password

    dialog.txt_password.setText("sample-password")
    dialog.txt_password.setCursorPosition(6)
    hidden_icon_key = dialog.btn_toggle_password.icon().cacheKey()
    dialog.btn_toggle_password.click()
    assert dialog.btn_toggle_password.icon().cacheKey() != hidden_icon_key
    assert dialog.txt_password.echoMode() == QLineEdit.EchoMode.Normal
    assert dialog.txt_password.text() == "sample-password"
    assert dialog.txt_password.cursorPosition() == 6
    assert dialog.btn_toggle_password.accessibleName() == "Sembunyikan kata sandi"

    visible_icon_key = dialog.btn_toggle_password.icon().cacheKey()
    dialog.btn_toggle_password.click()
    assert dialog.btn_toggle_password.icon().cacheKey() != visible_icon_key
    assert dialog.txt_password.echoMode() == QLineEdit.EchoMode.Password
    assert dialog.txt_password.text() == "sample-password"
    assert dialog.btn_toggle_password.accessibleName() == "Tampilkan kata sandi"


def test_login_dialog_uses_selected_theme_for_its_form(monkeypatch):
    from PyQt6.QtWidgets import QApplication

    from auth import LoginDialog
    from noc_brand import DARK_THEME, LIGHT_THEME

    application = QApplication.instance() or QApplication([])
    previous_theme = application.property("nocTheme")
    monkeypatch.setattr(
        "auth.check_active_license",
        lambda: (True, "Lisensi Aktif", 30, "2026-11-10"),
    )
    expected_styles = {
        DARK_THEME: ("#080D16", "#101E30"),
        LIGHT_THEME: ("#E8F0F9", "#F4F8FD"),
    }
    try:
        for theme_name, (background, form_background) in expected_styles.items():
            application.setProperty("nocTheme", theme_name)
            dialog = LoginDialog()
            try:
                self_style = dialog.styleSheet()
                assert background in self_style
                assert form_background in self_style
                assert dialog.theme_selector.isHidden() is False
                assert dialog.theme_selector.light_button.isChecked() == (
                    theme_name == LIGHT_THEME
                )
                assert dialog.theme_selector.dark_button.isChecked() == (
                    theme_name == DARK_THEME
                )
                assert dialog.txt_username.isEnabled()
                assert dialog.txt_password.isEnabled()
                assert not dialog.windowIcon().isNull()
            finally:
                dialog.close()
    finally:
        application.setProperty("nocTheme", previous_theme)


def test_login_theme_selector_updates_and_persists_theme(tmp_path, monkeypatch):
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication

    from auth import LoginDialog
    from noc_brand import DARK_THEME, LIGHT_THEME

    application = QApplication.instance() or QApplication([])
    previous_theme = application.property("nocTheme")
    previous_stylesheet = application.styleSheet()
    previous_icon = application.windowIcon()
    settings = QSettings(
        str(tmp_path / "settings.ini"),
        QSettings.Format.IniFormat,
    )
    monkeypatch.setattr("auth.display_settings", lambda: settings)
    monkeypatch.setattr(
        "auth.check_active_license",
        lambda: (True, "Lisensi Aktif", 30, "2026-11-10"),
    )
    dialog = LoginDialog()
    try:
        dialog.theme_selector.light_button.click()
        assert dialog.current_theme_name == LIGHT_THEME
        assert application.property("nocTheme") == LIGHT_THEME
        assert settings.value("appearance/theme") == LIGHT_THEME
        assert "#E8F0F9" in dialog.styleSheet()
        assert "#F2F6FC" in application.styleSheet()

        dialog.theme_selector.dark_button.click()
        assert dialog.current_theme_name == DARK_THEME
        assert application.property("nocTheme") == DARK_THEME
        assert settings.value("appearance/theme") == DARK_THEME
        assert "#080D16" in dialog.styleSheet()
        assert "#091526" in application.styleSheet()
    finally:
        dialog.close()
        application.setStyleSheet(previous_stylesheet)
        application.setProperty("nocTheme", previous_theme)
        application.setWindowIcon(previous_icon)


def test_forgot_password_dialog_shows_requested_plain_text(monkeypatch):
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from auth import LoginDialog

    _ = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "auth.check_active_license",
        lambda: (True, "Lisensi Aktif", 30, "2026-11-10"),
    )
    captured = {}

    def capture_dialog(dialog):
        captured["title"] = dialog.windowTitle()
        captured["message"] = dialog.text()
        captured["details"] = dialog.informativeText()
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "exec", capture_dialog)
    dialog = LoginDialog()
    dialog._handle_forgot_password()

    assert captured["title"] == "Bantuan Akses Akun"
    assert captured["message"] == "<b>Akses Dibatasi</b>"
    assert captured["details"] == (
        "Untuk alasan keamanan aplikasi dan kebahagiaan developer reset "
        "kata sandi mandiri tidak diperbolehkan.\n\n"
        'Silahkan hubungi Developer tools ini, "BANG BERT" untuk '
        "verifikasi identitas anda."
    )
