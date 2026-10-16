"""Tests for the Cloudflare-backed administrator desktop interface."""
from __future__ import annotations

import os
import time
from PyQt6.QtCore import QPoint, QThread

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QFrame, QInputDialog, QMessageBox

import noc_tools_admin
from cloudflare_api import WorkerApiError
from noc_brand import NocLogoMark


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def wait_for_admin_tasks(qt_app, window, timeout=5):
    deadline = time.monotonic() + timeout
    while window._request_thread is not None and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.005)
    qt_app.processEvents()
    assert window._request_thread is None


@pytest.fixture(autouse=True)
def clear_api_url_environment(monkeypatch):
    monkeypatch.setenv("NOC_LICENSE_API_URL", "")


class FakeAdminApi:
    def __init__(self, api_url=None):
        self.api_url = api_url
        self.is_authenticated = False
        self.users = [
            {
                "username": "operator",
                "display_name": "NOC Operator",
                "role": "operator",
                "is_active": 1,
            }
        ]
        self.licenses = []
        self.deleted_license_counts = {"deleted_licenses": 0, "cleared_activations": 0}
        self.calls = []
        self.request_threads = []
        self.bootstrap_required = True

    def _record_request_thread(self):
        self.request_threads.append(QThread.currentThread())

    def bootstrap_status(self):
        self._record_request_thread()
        return self.bootstrap_required

    def bootstrap(self, secret, username, display_name, password):
        self._record_request_thread()
        self.calls.append(("bootstrap", secret, username, display_name, password))

    def login(self, username, password):
        self._record_request_thread()
        self.calls.append(("login", username, password))
        self.is_authenticated = True

    def logout(self):
        self._record_request_thread()
        self.calls.append(("logout",))
        self.is_authenticated = False

    def list_users(self):
        self._record_request_thread()
        return self.users

    def list_licenses(self):
        self._record_request_thread()
        return self.licenses

    def delete_expired_licenses(self):
        self._record_request_thread()
        self.calls.append(("delete-expired-licenses",))
        expired = [
            license_item
            for license_item in self.licenses
            if license_item.get("status") == "expired"
        ]
        self.licenses = [
            license_item
            for license_item in self.licenses
            if license_item.get("status") != "expired"
        ]
        self.deleted_license_counts = {
            "deleted_licenses": len(expired),
            "cleared_activations": len(expired),
        }
        return self.deleted_license_counts

    def issue_license(self, email, machine_id, days, operator):
        self._record_request_thread()
        self.calls.append(("issue", email, machine_id, days, operator))
        self.licenses.append(
            {
                "email": email,
                "machine_id": machine_id,
                "days_valid": days,
                "operator": operator,
                "issued_at": 1_700_000_000,
            }
        )
        return "NOC-LIC3-signed-key"

    def create_user(self, username, display_name, password):
        self._record_request_thread()
        self.calls.append(("create-user", username, display_name, password))

    def reset_password(self, username, password):
        self._record_request_thread()
        self.calls.append(("reset-password", username, password))

    def set_user_active(self, username, active):
        self._record_request_thread()
        self.calls.append(("set-active", username, active))
        self.users[0]["is_active"] = int(active)


def test_noc_logo_mark_renders_the_blue_double_slash(qt_app):
    logo = NocLogoMark(100)
    logo.show()
    qt_app.processEvents()
    image = logo.grab().toImage()

    left_slash = image.pixelColor(QPoint(20, 50))
    right_slash = image.pixelColor(QPoint(75, 50))
    assert left_slash.alpha() > 0 and left_slash.blue() > left_slash.red()
    assert right_slash.alpha() > 0 and right_slash.blue() > right_slash.red()
    logo.close()


def test_login_switches_to_admin_and_displays_worker_data(monkeypatch, qt_app):
    created = []

    def api_factory(url):
        api = FakeAdminApi(url)
        created.append(api)
        return api

    monkeypatch.setattr(noc_tools_admin, "NocAdminApi", api_factory)
    window = noc_tools_admin.NocToolsAdminWindow()
    assert not window.windowIcon().isNull()
    assert window.findChild(NocLogoMark) is not None
    window.txt_api_url.setText("https://example.workers.dev")
    window.txt_username.setText("admin")
    window.txt_password.setText("StrongAdminPassword!2026")

    window._login()
    wait_for_admin_tasks(qt_app, window)

    assert window.stack.currentIndex() == 1
    assert window.user_table.item(0, 0).text() == "operator"
    assert window.user_table.item(0, 3).text() == "Active"
    assert window.btn_login.text() == "SIGN IN AS ADMINISTRATOR  ➔"
    assert window.txt_username.placeholderText() == "Administrator username"
    assert created[0].calls == [
        ("login", "admin", "StrongAdminPassword!2026")
    ]
    assert len(created[0].request_threads) >= 3
    assert all(thread is not qt_app.thread() for thread in created[0].request_threads)
    window.close()


def test_admin_access_page_reuses_noc_tools_login_visuals(monkeypatch, qt_app):
    api = FakeAdminApi()
    api.bootstrap_required = False
    monkeypatch.setenv("NOC_LICENSE_API_URL", "https://example.workers.dev")
    monkeypatch.setattr(noc_tools_admin, "NocAdminApi", lambda _url: api)

    window = noc_tools_admin.NocToolsAdminWindow()
    wait_for_admin_tasks(qt_app, window)

    assert window.size().width() == 960
    assert window.findChild(noc_tools_admin._NetworkPanel) is not None
    assert window.findChild(QFrame, "loginShell") is not None
    assert window.btn_login.objectName() == "btnLogin"
    assert window.btn_connection_settings.text() == "Connection settings"
    assert window.stack.currentIndex() == 0
    assert window.bootstrap_section.isHidden()
    window.close()


def test_admin_uses_official_worker_url_when_environment_is_unset(
    monkeypatch, qt_app
):
    api = FakeAdminApi()
    api.bootstrap_required = False
    monkeypatch.delenv("NOC_LICENSE_API_URL", raising=False)
    monkeypatch.setattr(noc_tools_admin, "NocAdminApi", lambda url: (
        setattr(api, "api_url", url) or api
    ))

    window = noc_tools_admin.NocToolsAdminWindow()
    wait_for_admin_tasks(qt_app, window)

    assert window.txt_api_url.text() == (
        "https://noc-license-api.pasitumeangroberto.workers.dev"
    )
    assert api.api_url == window.txt_api_url.text()
    window.close()


def test_first_admin_bootstrap_uses_fields_then_clears_setup_secrets(
    monkeypatch, qt_app
):
    created = []

    def api_factory(url):
        api = FakeAdminApi(url)
        created.append(api)
        return api

    monkeypatch.setattr(noc_tools_admin, "NocAdminApi", api_factory)
    window = noc_tools_admin.NocToolsAdminWindow()
    window.txt_api_url.setText("https://example.workers.dev")
    window.txt_username.setText("first-admin")
    window.txt_admin_display.setText("NOC Administrator")
    window.txt_bootstrap_secret.setText("one-time-secret")
    window.txt_bootstrap_password.setText("StrongAdminPassword!2026")

    window._bootstrap()
    wait_for_admin_tasks(qt_app, window)

    assert window.stack.currentIndex() == 1
    assert window.txt_bootstrap_secret.text() == ""
    assert window.txt_bootstrap_password.text() == ""
    assert created[0].calls == [
        (
            "bootstrap",
            "one-time-secret",
            "first-admin",
            "NOC Administrator",
            "StrongAdminPassword!2026",
        ),
        ("login", "first-admin", "StrongAdminPassword!2026"),
    ]
    window.close()


def test_existing_admin_hides_first_admin_setup_fields(monkeypatch, qt_app):
    api = FakeAdminApi()
    api.bootstrap_required = False
    monkeypatch.setattr(noc_tools_admin, "NocAdminApi", lambda _url: api)
    window = noc_tools_admin.NocToolsAdminWindow()
    window.txt_api_url.setText("https://example.workers.dev")

    window.txt_api_url.editingFinished.emit()
    wait_for_admin_tasks(qt_app, window)

    assert window.bootstrap_section.isHidden()
    assert window.btn_bootstrap.isHidden()
    assert not window.txt_username.isHidden()
    assert not window.txt_password.isHidden()
    assert window.connection_section.isHidden()
    assert "#080D16" in window.styleSheet()
    assert "#126DE8" in window.styleSheet()
    window.txt_api_url.clear()
    window.txt_api_url.editingFinished.emit()
    assert window.bootstrap_section.isHidden()
    assert window.btn_bootstrap.isHidden()
    assert not window.connection_section.isHidden()
    window.close()


def test_configured_worker_status_is_checked_on_startup(monkeypatch, qt_app):
    api = FakeAdminApi()
    api.bootstrap_required = False
    monkeypatch.setenv("NOC_LICENSE_API_URL", "https://example.workers.dev")
    monkeypatch.setattr(noc_tools_admin, "NocAdminApi", lambda _url: api)

    window = noc_tools_admin.NocToolsAdminWindow()
    wait_for_admin_tasks(qt_app, window)

    assert window.bootstrap_section.isHidden()
    assert window.btn_bootstrap.isHidden()
    assert window.connection_section.isHidden()
    window.close()


def test_startup_worker_status_check_runs_off_the_gui_thread(monkeypatch, qt_app):
    worker_thread = []

    class ThreadCheckingApi(FakeAdminApi):
        def bootstrap_status(self):
            worker_thread.append(QThread.currentThread())
            return False

    monkeypatch.setenv("NOC_LICENSE_API_URL", "https://example.workers.dev")
    monkeypatch.setattr(noc_tools_admin, "NocAdminApi", ThreadCheckingApi)

    window = noc_tools_admin.NocToolsAdminWindow()
    gui_thread = qt_app.thread()
    assert window._request_thread is not None
    assert not window.btn_login.isEnabled()
    wait_for_admin_tasks(qt_app, window)

    assert len(worker_thread) == 1
    assert worker_thread[0] is not gui_thread
    assert window.btn_login.isEnabled()
    window.close()


def test_setup_fields_only_appear_when_worker_requires_bootstrap(monkeypatch, qt_app):
    api = FakeAdminApi()
    api.bootstrap_required = True
    monkeypatch.setenv("NOC_LICENSE_API_URL", "https://example.workers.dev")
    monkeypatch.setattr(noc_tools_admin, "NocAdminApi", lambda _url: api)

    window = noc_tools_admin.NocToolsAdminWindow()
    wait_for_admin_tasks(qt_app, window)

    assert not window.bootstrap_section.isHidden()
    assert not window.btn_bootstrap.isHidden()
    assert not window.txt_username.isHidden()
    assert not window.txt_password.isHidden()
    window.close()


def test_worker_status_failure_does_not_show_setup_fields(monkeypatch, qt_app):
    class UnavailableApi(FakeAdminApi):
        def bootstrap_status(self):
            raise WorkerApiError("Layanan tidak tersedia.")

    monkeypatch.setenv("NOC_LICENSE_API_URL", "https://example.workers.dev")
    monkeypatch.setattr(noc_tools_admin, "NocAdminApi", UnavailableApi)

    window = noc_tools_admin.NocToolsAdminWindow()
    wait_for_admin_tasks(qt_app, window)

    assert window.bootstrap_section.isHidden()
    assert window.btn_bootstrap.isHidden()
    assert not window.connection_section.isHidden()
    assert "Layanan tidak tersedia" in window.lbl_access_status.text()
    window.close()


def test_license_and_operator_actions_call_cloudflare_api(
    monkeypatch, qt_app
):
    api = FakeAdminApi()
    api.is_authenticated = True
    warnings = []
    monkeypatch.setattr(noc_tools_admin, "NocAdminApi", lambda _url: api)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: warnings.append(args[1:3]),
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args: None,
    )
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *args, **kwargs: ("NewOperatorPassword!2026", True),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window = noc_tools_admin.NocToolsAdminWindow()
    window._api = api
    window.stack.setCurrentIndex(1)
    window.txt_license_email.setText("operator@example.com")
    window.txt_license_machine.setText("NOC-AAAA-BBBB-CCCC-DDDD")
    window.spin_days.setValue(60)
    window.txt_operator.setText("NOC_Operator")

    window._issue_license()
    wait_for_admin_tasks(qt_app, window)

    assert window.txt_license_key.text() == "NOC-LIC3-signed-key"
    assert window.license_table.item(0, 0).text() == "operator@example.com"
    assert ("issue", "operator@example.com", "NOC-AAAA-BBBB-CCCC-DDDD", 60, "NOC_Operator") in api.calls

    window.txt_new_username.setText("new-operator")
    window.txt_new_display.setText("New Operator")
    window.txt_new_password.setText("InitialOperatorPassword!2026")
    window._create_user()
    wait_for_admin_tasks(qt_app, window)
    assert (
        "create-user",
        "new-operator",
        "New Operator",
        "InitialOperatorPassword!2026",
    ) in api.calls
    assert window.txt_new_password.text() == ""

    window.user_table.selectRow(0)
    window._reset_selected_password()
    wait_for_admin_tasks(qt_app, window)
    assert ("reset-password", "operator", "NewOperatorPassword!2026") in api.calls
    window._toggle_selected_user()
    wait_for_admin_tasks(qt_app, window)
    assert ("set-active", "operator", False) in api.calls
    assert window.user_table.item(0, 3).text() == "Inactive"
    assert warnings == []
    assert api.request_threads
    assert all(thread is not qt_app.thread() for thread in api.request_threads)
    window.close()


def test_failed_license_issue_clears_previous_key(monkeypatch, qt_app):
    class FailedIssueApi(FakeAdminApi):
        def issue_license(self, email, machine_id, days, operator):
            raise WorkerApiError("Machine ID tidak valid.")

    warnings = []
    monkeypatch.setattr(
        noc_tools_admin,
        "NocAdminApi",
        lambda _url: FailedIssueApi(),
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: warnings.append(args[1:3]),
    )
    window = noc_tools_admin.NocToolsAdminWindow()
    api = FailedIssueApi()
    api.is_authenticated = True
    window._api = api
    window.txt_license_key.setText("NOC-LIC3-old-key")
    window.txt_license_email.setText("operator@example.com")
    window.txt_license_machine.setText("NOC-INVALID")

    window._issue_license()
    assert window.txt_license_key.text() == ""
    wait_for_admin_tasks(qt_app, window)

    assert window.txt_license_key.text() == ""
    assert "Machine ID tidak valid." in window.lbl_license_status.text()
    assert warnings == [
        ("Unable to issue license", "Machine ID tidak valid.")
    ]
    window.close()


def test_cancelled_operator_status_change_does_not_call_api(
    monkeypatch, qt_app
):
    api = FakeAdminApi()
    api.is_authenticated = True
    confirmations = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: (
        confirmations.append(args[1:3]) or QMessageBox.StandardButton.No
    ))
    window = noc_tools_admin.NocToolsAdminWindow()
    window._api = api
    api.users = [
        {
            "username": "operator",
            "display_name": "NOC Operator",
            "role": "operator",
            "is_active": 1,
        }
    ]
    window._populate_users(api.users)
    window.user_table.selectRow(0)

    window._toggle_selected_user()

    assert confirmations == [
        (
            "Confirm account status change",
            "Are you sure you want to disable operator account 'operator'?",
        )
    ]
    assert api.calls == []
    assert window.user_table.item(0, 3).text() == "Active"
    window.close()


@pytest.mark.parametrize(
    ("initial_active", "expected_active", "expected_action", "expected_status"),
    [
        (1, False, "disable", "Inactive"),
        (0, True, "enable", "Active"),
    ],
)
def test_confirmed_operator_status_change_updates_api_and_refreshes_table(
    monkeypatch,
    qt_app,
    initial_active,
    expected_active,
    expected_action,
    expected_status,
):
    api = FakeAdminApi()
    api.is_authenticated = True
    api.users[0]["is_active"] = initial_active
    confirmations = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: (
            confirmations.append(args[1:3]) or QMessageBox.StandardButton.Yes
        ),
    )
    window = noc_tools_admin.NocToolsAdminWindow()
    window._api = api
    window._populate_users(api.users)
    window.user_table.selectRow(0)

    window._toggle_selected_user()
    wait_for_admin_tasks(qt_app, window)

    assert confirmations
    assert ("set-active", "operator", expected_active) in api.calls
    assert expected_action in confirmations[0][1]
    assert window.user_table.item(0, 3).text() == expected_status
    window.close()


def test_worker_errors_are_shown_without_switching_to_admin(monkeypatch, qt_app):
    class FailedApi(FakeAdminApi):
        def login(self, username, password):
            raise WorkerApiError("Username atau kata sandi administrator tidak valid.")

    messages = []
    monkeypatch.setattr(noc_tools_admin, "NocAdminApi", lambda _url: FailedApi(_url))
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: messages.append(args[1:3]),
    )
    window = noc_tools_admin.NocToolsAdminWindow()
    window.txt_api_url.setText("https://example.workers.dev")
    window.txt_username.setText("admin")
    window.txt_password.setText("wrong")

    window._login()
    wait_for_admin_tasks(qt_app, window)

    assert window.stack.currentIndex() == 0
    assert "tidak valid" in window.lbl_access_status.text()
    assert messages == [
        (
            "Administrator sign-in failed",
            "Username atau kata sandi administrator tidak valid.",
        )
    ]
    window.close()


def test_admin_account_cannot_be_toggled_from_operator_controls(
    monkeypatch, qt_app
):
    api = FakeAdminApi()
    api.is_authenticated = True
    api.users = [
        {
            "username": "admin",
            "display_name": "Administrator",
            "role": "admin",
            "is_active": 1,
        }
    ]
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args: messages.append(args[1:3]),
    )
    window = noc_tools_admin.NocToolsAdminWindow()
    window._api = api
    window._refresh_users()
    wait_for_admin_tasks(qt_app, window)
    window.user_table.selectRow(0)

    window._toggle_selected_user()

    assert api.calls == []
    assert messages == [
        (
            "Account cannot be changed",
            "Only operator accounts can be enabled or disabled.",
        )
    ]
    window.close()


def test_expired_license_cleanup_marks_rows_and_requires_confirmation(
    monkeypatch, qt_app
):
    api = FakeAdminApi()
    api.is_authenticated = True
    api.licenses = [
        {
            "email": "expired@example.com",
            "machine_id": "NOC-AAAA-BBBB-CCCC-DDDD",
            "days_valid": 30,
            "operator": "NOC_Operator",
            "issued_at": 1_700_000_000,
            "expires_at": 1_700_000_001,
            "status": "expired",
        },
        {
            "email": "active@example.com",
            "machine_id": "NOC-EEEE-FFFF-GGGG-HHHH",
            "days_valid": 60,
            "operator": "NOC_Operator",
            "issued_at": 1_700_000_000,
            "expires_at": 1_900_000_000,
            "status": "active",
        },
        {
            "email": "pending@example.com",
            "machine_id": "NOC-IIII-JJJJ-KKKK-LLLL",
            "days_valid": 90,
            "operator": "NOC_Operator",
            "issued_at": 1_700_000_000,
            "expires_at": None,
            "status": "not_activated",
        },
    ]
    confirmations = iter(
        (QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
    )
    monkeypatch.setattr(noc_tools_admin, "NocAdminApi", lambda _url: api)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: next(confirmations)
    )
    window = noc_tools_admin.NocToolsAdminWindow()
    window._api = api
    window._populate_licenses(api.licenses)

    expired_status = window.license_table.item(0, 6)
    assert expired_status.text() == "EXPIRED"
    assert expired_status.font().bold()
    assert expired_status.foreground().color().name() == "#ff0000"
    assert window.license_table.item(0, 5).text() == "2023-11-14 22:13 UTC"
    assert window.license_table.item(1, 6).text() == "ACTIVE"
    assert window.license_table.item(2, 6).text() == "NOT ACTIVATED"
    assert window.license_table.item(2, 5).text() == ""

    window._delete_expired_licenses()
    assert api.calls == []
    assert window.license_table.rowCount() == 3

    window._delete_expired_licenses()
    wait_for_admin_tasks(qt_app, window)

    assert api.calls == [("delete-expired-licenses",)]
    assert window.license_table.rowCount() == 2
    assert window.license_table.item(0, 6).text() == "ACTIVE"
    assert window.license_table.item(1, 6).text() == "NOT ACTIVATED"
    assert "Removed 1 expired license record(s)" in window.lbl_license_status.text()
    window.close()


def test_expired_license_cleanup_without_expired_rows_skips_confirmation(
    monkeypatch, qt_app
):
    api = FakeAdminApi()
    api.is_authenticated = True
    api.licenses = [{"email": "pending@example.com", "status": "not_activated"}]
    confirmations = []
    monkeypatch.setattr(noc_tools_admin, "NocAdminApi", lambda _url: api)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: confirmations.append(args),
    )
    window = noc_tools_admin.NocToolsAdminWindow()
    window._api = api
    window._populate_licenses(api.licenses)

    window._delete_expired_licenses()

    assert confirmations == []
    assert api.calls == []
    assert window.license_table.rowCount() == 1
    assert window.lbl_license_status.text() == "No expired licenses to delete."
    window.close()


def test_expired_license_cleanup_reports_worker_errors(
    monkeypatch, qt_app
):
    class FailedApi(FakeAdminApi):
        def delete_expired_licenses(self):
            self._record_request_thread()
            raise WorkerApiError("Cloudflare cleanup failed.")

    api = FailedApi()
    api.is_authenticated = True
    api.licenses = [{"email": "expired@example.com", "status": "expired"}]
    warnings = []
    monkeypatch.setattr(noc_tools_admin, "NocAdminApi", lambda _url: api)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *args: warnings.append(args[1:3])
    )
    window = noc_tools_admin.NocToolsAdminWindow()
    window._api = api
    window._populate_licenses(api.licenses)

    window._delete_expired_licenses()
    wait_for_admin_tasks(qt_app, window)

    assert "Cloudflare cleanup failed." in window.lbl_license_status.text()
    assert warnings == [
        ("Unable to delete licenses", "Cloudflare cleanup failed.")
    ]
    assert window.license_table.rowCount() == 1
    window.close()
