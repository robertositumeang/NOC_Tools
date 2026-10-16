"""Cloudflare-backed NOC Tools license and account administration desktop app."""
from __future__ import annotations

import os
import sys
from collections.abc import Callable
from datetime import datetime, timezone

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from auth import _LOGIN_QSS, _NetworkPanel
from cloudflare_api import NocAdminApi, WorkerApiError
from noc_brand import DARK_THEME, NocLogoMark, app_icon
from service_config import DEFAULT_LICENSE_API_URL, LICENSE_API_URL_ENV

_STYLE = _LOGIN_QSS + """
QMainWindow, QWidget#page {
    background: #080D16; color: #E6EDF7; font-family: 'Segoe UI';
}
QFrame#panel {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #101E30, stop:1 #0B1524);
    border: 1px solid #294463; border-radius: 14px;
}
QLabel#title { color: #F8FAFC; font-size: 24px; font-weight: 700; }
QLabel#subtitle, QLabel#muted { color: #91A9C7; }
QLabel#field, QLabel#fieldLabel {
    color: #AFC2DC; font-size: 10px; font-weight: 700; letter-spacing: 0.9px;
}
QLineEdit, QComboBox, QSpinBox {
    background: rgba(20, 36, 57, 0.88); color: #F1F5F9;
    border: 1px solid #294567; border-radius: 9px; padding: 11px 13px;
    selection-background-color: #1678F2;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #3289FF; background: #14243A;
}
QPushButton {
    background: #162032; color: #F8FAFC; border: 1px solid #1F2D42;
    border-radius: 7px; padding: 8px 13px; font-weight: 700;
}
QPushButton:hover { background: #1E2C44; border-color: #3289FF; }
QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #126DE8, stop:1 #148BFF);
    color: #FFFFFF; border: none; padding: 11px 20px; min-height: 38px;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #2582FF, stop:1 #40A2FF);
}
QPushButton#settings {
    background: transparent; color: #8796A9; border: none;
    text-align: right; padding: 3px 0;
}
QPushButton#settings:hover { color: #4EB7FF; text-decoration: underline; }
QPushButton#danger { color: #FF9CAA; }
QTableWidget {
    background: #0B111C; color: #E7EEF8; gridline-color: #263D59;
    border: 1px solid #263D59; border-radius: 8px;
}
QHeaderView::section {
    background: #162032; color: #AFC3DC; border: none; padding: 8px;
    font-weight: 700;
}
QTabWidget::pane { border: 1px solid #263D59; border-radius: 10px; top: -1px; }
QTabBar::tab { background: #101E30; color: #9DB2CB; padding: 10px 18px; }
QTabBar::tab:selected { background: #173454; color: #FFFFFF; }
"""


def _field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("field")
    return label


def _login_field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("fieldLabel")
    return label


class _AdminRequestThread(QThread):
    result_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, operation: Callable[[], object]) -> None:
        super().__init__()
        self._operation = operation

    def run(self) -> None:
        try:
            result = self._operation()
        except Exception as error:
            self.error_occurred.emit(str(error))
        else:
            self.result_ready.emit(result)


_ACTIVE_ADMIN_THREADS: set[_AdminRequestThread] = set()


class NocToolsAdminWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NOC Tools Administrator")
        self.setWindowIcon(app_icon(DARK_THEME))
        self.resize(960, 590)
        self.setMinimumSize(800, 560)
        self.setStyleSheet(_STYLE)
        self._api: NocAdminApi | None = None
        self._request_thread: _AdminRequestThread | None = None
        self._request_after_finished: Callable[[], None] | None = None
        self._build_ui()
        self._busy_widgets = [
            self.txt_api_url,
            self.btn_connection_settings,
            self.txt_username,
            self.txt_password,
            self.txt_bootstrap_secret,
            self.txt_admin_display,
            self.txt_bootstrap_password,
            self.btn_login,
            self.btn_bootstrap,
            self.btn_refresh,
            self.btn_logout,
            self.admin_tabs,
            self.txt_license_email,
            self.txt_license_machine,
            self.spin_days,
            self.txt_operator,
            self.btn_issue_license,
            self.btn_copy_license,
            self.btn_delete_expired_licenses,
            self.txt_new_username,
            self.txt_new_display,
            self.txt_new_password,
            self.btn_create_user,
            self.btn_reset_password,
            self.btn_toggle_user,
        ]
        self._check_bootstrap_status()

    def _build_ui(self) -> None:
        page = QWidget()
        page.setObjectName("page")
        self.setCentralWidget(page)
        root = QVBoxLayout(page)
        root.setContentsMargins(12, 12, 12, 12)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self._build_access_page()
        self._build_admin_page()

    def _build_access_page(self) -> None:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        shell = QFrame()
        shell.setObjectName("loginShell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        brand_panel = _NetworkPanel()
        brand_panel.setObjectName("brandPanel")
        brand_panel.setMinimumWidth(360)
        brand_layout = QVBoxLayout(brand_panel)
        brand_layout.setContentsMargins(32, 28, 30, 23)
        brand_layout.setSpacing(0)

        brand_header = QHBoxLayout()
        brand_header.setSpacing(11)
        brand_header.addWidget(NocLogoMark(42))
        brand_details = QVBoxLayout()
        brand_details.setSpacing(4)
        brand_title = QLabel("NOC Tools")
        brand_title.setObjectName("titleLabel")
        brand_title.setStyleSheet("font-size: 16px;")
        brand_details.addWidget(brand_title)
        brand_subtitle = QLabel("PT. KEREAKTIF Indonesia")
        brand_subtitle.setObjectName("subtitleLabel")
        brand_details.addWidget(brand_subtitle)
        brand_header.addLayout(brand_details)
        brand_header.addStretch()
        brand_layout.addLayout(brand_header)
        brand_layout.addStretch(2)

        eyebrow = QLabel("ADMINISTRATOR ACCESS")
        eyebrow.setObjectName("brandEyebrow")
        brand_layout.addWidget(eyebrow)
        brand_layout.addSpacing(12)
        brand_title = QLabel("NOC Tools")
        brand_title.setObjectName("titleLabel")
        brand_layout.addWidget(brand_title)
        brand_accent = QLabel("Administrator")
        brand_accent.setObjectName("showcaseAccent")
        brand_layout.addWidget(brand_accent)
        brand_layout.addSpacing(12)
        brand_copy = QLabel("Manage NOC administrator accounts and licenses.")
        brand_copy.setObjectName("formHint")
        brand_copy.setWordWrap(True)
        brand_copy.setMaximumWidth(370)
        brand_layout.addWidget(brand_copy)
        brand_layout.addStretch(1)
        brand_footer = QLabel("CONTROL PLANE  ·  SECURE ACCESS")
        brand_footer.setObjectName("trustBadge")
        brand_layout.addWidget(brand_footer)
        shell_layout.addWidget(brand_panel, 11)

        form_panel = QFrame()
        form_panel.setObjectName("formPanel")
        form_panel.setMaximumWidth(456)
        form = QVBoxLayout(form_panel)
        form.setContentsMargins(34, 34, 34, 25)
        form.setSpacing(9)
        form.addStretch(1)
        heading = QLabel("Administrator sign-in")
        heading.setObjectName("formTitle")
        form.addWidget(heading)
        hint = QLabel("Sign in to manage NOC Tools.")
        hint.setObjectName("formHint")
        form.addWidget(hint)
        form.addSpacing(6)

        self.txt_api_url = QLineEdit(
            os.environ.get(LICENSE_API_URL_ENV, DEFAULT_LICENSE_API_URL)
        )
        self.txt_api_url.setPlaceholderText("https://noc-license-api.<account>.workers.dev")
        self.txt_api_url.editingFinished.connect(self._check_bootstrap_status)
        self.connection_section = QWidget()
        connection_form = QVBoxLayout(self.connection_section)
        connection_form.setContentsMargins(0, 0, 0, 0)
        connection_form.setSpacing(8)
        connection_form.addWidget(_field_label("CLOUDFLARE WORKER URL"))
        connection_form.addWidget(self.txt_api_url)
        self.btn_connection_settings = QPushButton("Connection settings")
        self.btn_connection_settings.setObjectName("btnForgot")
        self.btn_connection_settings.setCheckable(True)
        self.btn_connection_settings.toggled.connect(
            self.connection_section.setVisible
        )
        form.addWidget(
            self.btn_connection_settings,
            alignment=Qt.AlignmentFlag.AlignRight,
        )
        form.addWidget(self.connection_section)
        self.connection_section.setVisible(not self.txt_api_url.text().strip())

        self.txt_username = QLineEdit()
        self.txt_username.setPlaceholderText("Administrator username")
        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("Administrator password")
        self.txt_username.returnPressed.connect(self.txt_password.setFocus)
        self.txt_password.returnPressed.connect(self._login)
        for caption, widget in (
            ("USERNAME", self.txt_username),
            ("PASSWORD", self.txt_password),
        ):
            form.addWidget(_login_field_label(caption))
            form.addWidget(widget)

        self.txt_bootstrap_secret = QLineEdit()
        self.txt_bootstrap_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_bootstrap_secret.setPlaceholderText("One-time setup secret from Cloudflare")
        self.txt_admin_display = QLineEdit()
        self.txt_admin_display.setPlaceholderText("Administrator name")
        self.txt_bootstrap_password = QLineEdit()
        self.txt_bootstrap_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_bootstrap_password.setPlaceholderText("New password, at least 12 characters")
        self.bootstrap_section = QWidget()
        bootstrap_form = QVBoxLayout(self.bootstrap_section)
        bootstrap_form.setContentsMargins(0, 0, 0, 0)
        bootstrap_form.setSpacing(10)
        for caption, widget in (
            ("ONE-TIME SETUP SECRET", self.txt_bootstrap_secret),
            ("FIRST ADMINISTRATOR NAME", self.txt_admin_display),
            ("FIRST ADMINISTRATOR PASSWORD", self.txt_bootstrap_password),
        ):
            bootstrap_form.addWidget(_login_field_label(caption))
            bootstrap_form.addWidget(widget)
        form.addWidget(self.bootstrap_section)
        self.bootstrap_section.hide()

        self.btn_login = QPushButton("SIGN IN AS ADMINISTRATOR  ➔")
        self.btn_login.setObjectName("btnLogin")
        self.btn_login.setDefault(True)
        self.btn_login.clicked.connect(self._login)
        self.btn_bootstrap = QPushButton("Create first administrator")
        self.btn_bootstrap.clicked.connect(self._bootstrap)
        form.addWidget(self.btn_login)
        form.addWidget(self.btn_bootstrap)
        self.btn_bootstrap.hide()
        self.lbl_access_status = QLabel("")
        self.lbl_access_status.setWordWrap(True)
        self.lbl_access_status.setObjectName("errorLabel")
        form.addWidget(self.lbl_access_status)
        form.addStretch(1)

        shell_layout.addWidget(form_panel, 9)
        page_layout.addWidget(shell)
        self.stack.addWidget(page)

    def _set_bootstrap_status(
        self,
        required: bool | None,
        message: str = "",
    ) -> None:
        show_setup = required is True
        self.bootstrap_section.setVisible(show_setup)
        self.btn_bootstrap.setVisible(show_setup)
        self.lbl_access_status.setText(message)
        self.resize(960, 700 if show_setup else 590)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        for widget in self._busy_widgets:
            widget.setEnabled(not busy)
        self.setCursor(Qt.CursorShape.WaitCursor if busy else Qt.CursorShape.ArrowCursor)
        self.lbl_admin_status.setText(message if busy else "")
        self.lbl_admin_status.setVisible(busy)
        if busy and self.stack.currentIndex() == 0:
            self.lbl_access_status.setText(message)

    def _run_request(
        self,
        operation: Callable[[], object],
        on_success: Callable[[object], None],
        *,
        busy_message: str,
        on_error: Callable[[str], None] | None = None,
    ) -> bool:
        if self._request_thread is not None:
            return False

        thread = _AdminRequestThread(operation)
        self._request_thread = thread
        self._set_busy(True, busy_message)
        thread.result_ready.connect(
            on_success,
            Qt.ConnectionType.QueuedConnection,
        )
        thread.error_occurred.connect(
            on_error
            or (
                lambda message: QMessageBox.warning(
                    self,
                    "Administrator request failed",
                    message,
                )
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        thread.finished.connect(
            lambda completed=thread: _ACTIVE_ADMIN_THREADS.discard(completed)
        )
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda completed=thread: self._request_finished(completed),
            Qt.ConnectionType.QueuedConnection,
        )
        _ACTIVE_ADMIN_THREADS.add(thread)
        thread.start()
        return True

    def _request_finished(self, thread: _AdminRequestThread) -> None:
        if self._request_thread is not thread:
            return
        self._request_thread = None
        self._set_busy(False)
        after_finished = self._request_after_finished
        self._request_after_finished = None
        if after_finished is not None:
            after_finished()

    def _check_bootstrap_status(self) -> None:
        api_url = self.txt_api_url.text().strip()
        if not api_url:
            self._set_bootstrap_status(
                None,
                "Cloudflare Worker URL is not configured.",
            )
            self.connection_section.setVisible(True)
            self.btn_connection_settings.setChecked(True)
            return

        def on_success(required: object) -> None:
            self._set_bootstrap_status(
                required if isinstance(required, bool) else None,
                (
                    "No administrator exists yet. Complete the one-time setup."
                    if required is True
                    else ""
                ),
            )
            self.connection_section.setVisible(False)
            self.btn_connection_settings.setChecked(False)

        def on_error(message: str) -> None:
            self._set_bootstrap_status(
                None,
                f"Unable to check administrator status: {message}",
            )
            self.connection_section.setVisible(True)
            self.btn_connection_settings.setChecked(True)

        self._run_request(
            lambda: NocAdminApi(api_url).bootstrap_status(),
            on_success,
            busy_message="Checking administrator setup...",
            on_error=on_error,
        )

    def _build_admin_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        toolbar = QHBoxLayout()
        self.lbl_admin_identity = QLabel("")
        self.lbl_admin_identity.setObjectName("muted")
        toolbar.addWidget(self.lbl_admin_identity)
        self.lbl_admin_status = QLabel("")
        self.lbl_admin_status.setObjectName("muted")
        self.lbl_admin_status.hide()
        toolbar.addWidget(self.lbl_admin_status)
        toolbar.addStretch()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self._refresh_all)
        self.btn_logout = QPushButton("Sign out")
        self.btn_logout.clicked.connect(self._logout)
        toolbar.addWidget(self.btn_refresh)
        toolbar.addWidget(self.btn_logout)
        layout.addLayout(toolbar)

        self.admin_tabs = QTabWidget()
        self.admin_tabs.addTab(self._build_license_tab(), "Licenses")
        self.admin_tabs.addTab(self._build_users_tab(), "Accounts & passwords")
        layout.addWidget(self.admin_tabs, 1)
        self.stack.addWidget(page)

    def _build_license_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        panel = QFrame()
        panel.setObjectName("panel")
        form = QFormLayout(panel)
        form.setContentsMargins(18, 18, 18, 18)
        self.txt_license_email = QLineEdit()
        self.txt_license_email.setPlaceholderText("name@company.com")
        self.txt_license_machine = QLineEdit()
        self.txt_license_machine.setPlaceholderText("NOC-XXXX-XXXX-XXXX-XXXX")
        self.spin_days = QSpinBox()
        self.spin_days.setRange(1, 3650)
        self.spin_days.setValue(30)
        self.txt_operator = QLineEdit("NOC_Operator")
        form.addRow(_field_label("EMAIL"), self.txt_license_email)
        form.addRow(_field_label("MACHINE ID"), self.txt_license_machine)
        form.addRow(_field_label("DURATION (DAYS)"), self.spin_days)
        form.addRow(_field_label("OPERATOR"), self.txt_operator)

        self.btn_issue_license = QPushButton("Issue license key")
        self.btn_issue_license.setObjectName("primary")
        self.btn_issue_license.clicked.connect(self._issue_license)
        self.txt_license_key = QLineEdit()
        self.txt_license_key.setReadOnly(True)
        self.txt_license_key.setPlaceholderText("The license key will appear here")
        self.btn_copy_license = QPushButton("Copy")
        self.btn_copy_license.clicked.connect(self._copy_license)
        key_row = QHBoxLayout()
        key_row.addWidget(self.txt_license_key, 1)
        key_row.addWidget(self.btn_copy_license)
        self.lbl_license_status = QLabel("")
        layout.addWidget(panel)
        layout.addWidget(self.btn_issue_license)
        layout.addLayout(key_row)
        layout.addWidget(self.lbl_license_status)
        layout.addSpacing(12)
        layout.addWidget(_field_label("ISSUED LICENSES"))
        license_actions = QHBoxLayout()
        license_actions.addStretch()
        self.btn_delete_expired_licenses = QPushButton("Delete expired licenses")
        self.btn_delete_expired_licenses.setObjectName("danger")
        self.btn_delete_expired_licenses.clicked.connect(
            self._delete_expired_licenses
        )
        license_actions.addWidget(self.btn_delete_expired_licenses)
        layout.addLayout(license_actions)

        self.license_table = QTableWidget(0, 7)
        self.license_table.setHorizontalHeaderLabels(
            [
                "Email",
                "Machine ID",
                "Days",
                "Operator",
                "Issued at",
                "Expires at",
                "Status",
            ]
        )
        self.license_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.license_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.license_table, 1)
        return page

    def _build_users_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        panel = QFrame()
        panel.setObjectName("panel")
        form = QFormLayout(panel)
        form.setContentsMargins(18, 18, 18, 18)
        self.txt_new_username = QLineEdit()
        self.txt_new_username.setPlaceholderText("Login username")
        self.txt_new_display = QLineEdit()
        self.txt_new_display.setPlaceholderText("Display name")
        self.txt_new_password = QLineEdit()
        self.txt_new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_new_password.setPlaceholderText("At least 12 characters")
        form.addRow(_field_label("USERNAME"), self.txt_new_username)
        form.addRow(_field_label("DISPLAY NAME"), self.txt_new_display)
        form.addRow(_field_label("INITIAL PASSWORD"), self.txt_new_password)
        self.btn_create_user = QPushButton("Create operator account")
        self.btn_create_user.setObjectName("primary")
        self.btn_create_user.clicked.connect(self._create_user)
        layout.addWidget(panel)
        layout.addWidget(self.btn_create_user)
        actions = QHBoxLayout()
        self.btn_reset_password = QPushButton("Reset selected account password")
        self.btn_reset_password.clicked.connect(self._reset_selected_password)
        self.btn_toggle_user = QPushButton("Enable / disable selected account")
        self.btn_toggle_user.clicked.connect(self._toggle_selected_user)
        actions.addWidget(self.btn_reset_password)
        actions.addWidget(self.btn_toggle_user)
        layout.addLayout(actions)
        self.user_table = QTableWidget(0, 4)
        self.user_table.setHorizontalHeaderLabels(
            ["Username", "Display name", "Role", "Status"]
        )
        self.user_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.user_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.user_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.user_table, 1)
        return page

    def _login(self) -> None:
        api_url = self.txt_api_url.text().strip()
        username = self.txt_username.text().strip()
        password = self.txt_password.text()

        def operation() -> tuple[NocAdminApi, str]:
            api = NocAdminApi(api_url)
            api.login(username, password)
            return api, username

        def on_success(result: object) -> None:
            api, signed_in_as = result
            self._api = api
            self.lbl_admin_identity.setText(f"Signed in as {signed_in_as}")
            self.txt_password.clear()
            self.lbl_access_status.clear()
            self.stack.setCurrentIndex(1)
            self._request_after_finished = self._refresh_all

        def on_error(message: str) -> None:
            self.lbl_access_status.setText(message)
            QMessageBox.warning(self, "Administrator sign-in failed", message)

        self._run_request(
            operation,
            on_success,
            busy_message="Signing in...",
            on_error=on_error,
        )

    def _bootstrap(self) -> None:
        api_url = self.txt_api_url.text().strip()
        username = self.txt_username.text().strip()
        display_name = self.txt_admin_display.text().strip()
        bootstrap_secret = self.txt_bootstrap_secret.text()
        password = self.txt_bootstrap_password.text()

        def operation() -> tuple[NocAdminApi, str]:
            api = NocAdminApi(api_url)
            if not api.bootstrap_status():
                raise WorkerApiError("Administrator setup has already been completed.")
            api.bootstrap(bootstrap_secret, username, display_name, password)
            api.login(username, password)
            return api, username

        def on_success(result: object) -> None:
            api, signed_in_as = result
            self._api = api
            self.lbl_admin_identity.setText(f"Signed in as {signed_in_as}")
            self.stack.setCurrentIndex(1)
            self.txt_bootstrap_secret.clear()
            self.txt_bootstrap_password.clear()
            self._request_after_finished = self._refresh_all

        def on_error(message: str) -> None:
            self.lbl_access_status.setText(message)
            QMessageBox.warning(self, "Administrator setup failed", message)

        self._run_request(
            operation,
            on_success,
            busy_message="Creating administrator account...",
            on_error=on_error,
        )

    def _require_api(self) -> NocAdminApi:
        if self._api is None or not self._api.is_authenticated:
            raise WorkerApiError("Administrator session is inactive. Please sign in again.")
        return self._api

    def _refresh_all(self) -> None:
        try:
            api = self._require_api()
        except WorkerApiError as error:
            QMessageBox.warning(self, "Unable to load data", str(error))
            return

        def operation() -> tuple[list[dict], list[dict]]:
            return api.list_users(), api.list_licenses()

        def on_success(result: object) -> None:
            users, licenses = result
            self._populate_users(users)
            self._populate_licenses(licenses)

        self._run_request(
            operation,
            on_success,
            busy_message="Loading accounts and licenses...",
            on_error=lambda message: QMessageBox.warning(
                self,
                "Unable to load data",
                message,
            ),
        )

    def _refresh_users(self) -> None:
        try:
            api = self._require_api()
        except WorkerApiError as error:
            QMessageBox.warning(self, "Unable to load accounts", str(error))
            return

        self._run_request(
            api.list_users,
            lambda users: self._populate_users(users),
            busy_message="Loading accounts...",
            on_error=lambda message: QMessageBox.warning(
                self,
                "Unable to load accounts",
                message,
            ),
        )

    def _populate_users(self, users: list[dict]) -> None:
        self.user_table.setRowCount(len(users))
        for row, user in enumerate(users):
            values = (
                user.get("username", ""),
                user.get("display_name", ""),
                user.get("role", ""),
                "Active" if user.get("is_active") == 1 else "Inactive",
            )
            for column, value in enumerate(values):
                self.user_table.setItem(row, column, QTableWidgetItem(str(value)))

    def _refresh_licenses(self) -> None:
        try:
            api = self._require_api()
        except WorkerApiError as error:
            QMessageBox.warning(self, "Unable to load licenses", str(error))
            return

        self._run_request(
            api.list_licenses,
            lambda licenses: self._populate_licenses(licenses),
            busy_message="Loading licenses...",
            on_error=lambda message: QMessageBox.warning(
                self,
                "Unable to load licenses",
                message,
            ),
        )

    def _populate_licenses(self, licenses: list[dict]) -> None:
        self.license_table.setRowCount(len(licenses))
        for row, item in enumerate(licenses):
            issued = self._format_license_timestamp(item.get("issued_at"))
            expires = self._format_license_timestamp(item.get("expires_at"))
            status = str(item.get("status") or "not_activated").casefold()
            status_labels = {
                "active": "ACTIVE",
                "expired": "EXPIRED",
                "not_activated": "NOT ACTIVATED",
            }
            values = (
                item.get("email", ""),
                item.get("machine_id", ""),
                item.get("days_valid", ""),
                item.get("operator", ""),
                issued,
                expires,
                status_labels.get(status, "UNKNOWN"),
            )
            for column, value in enumerate(values):
                table_item = QTableWidgetItem(str(value))
                if status == "expired":
                    table_item.setForeground(Qt.GlobalColor.red)
                    font = table_item.font()
                    font.setBold(True)
                    table_item.setFont(font)
                self.license_table.setItem(row, column, table_item)

    @staticmethod
    def _format_license_timestamp(timestamp: object) -> str:
        if (
            isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
        ):
            return ""
        return datetime.fromtimestamp(timestamp, timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC"
        )

    def _delete_expired_licenses(self) -> None:
        expired_count = sum(
            self.license_table.item(row, 6) is not None
            and self.license_table.item(row, 6).text() == "EXPIRED"
            for row in range(self.license_table.rowCount())
        )
        if expired_count == 0:
            self.lbl_license_status.setText("No expired licenses to delete.")
            return
        confirmation = QMessageBox.question(
            self,
            "Delete expired licenses",
            (
                f"Delete {expired_count} expired license record(s) and clear "
                "expired device bindings? Activation history will be retained "
                "to prevent old keys from being reused."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        try:
            api = self._require_api()
        except WorkerApiError as error:
            self.lbl_license_status.setText(
                f"Expired licenses were not deleted: {error}"
            )
            QMessageBox.warning(self, "Unable to delete licenses", str(error))
            return

        def on_success(result: object) -> None:
            deleted = result["deleted_licenses"]
            cleared = result["cleared_activations"]
            self.lbl_license_status.setText(
                f"Removed {deleted} expired license record(s); "
                f"cleared {cleared} expired device binding(s)."
            )
            self._request_after_finished = self._refresh_licenses

        def on_error(message: str) -> None:
            self.lbl_license_status.setText(
                f"Expired licenses were not deleted: {message}"
            )
            QMessageBox.warning(self, "Unable to delete licenses", message)

        self._run_request(
            api.delete_expired_licenses,
            on_success,
            busy_message="Deleting expired licenses...",
            on_error=on_error,
        )

    def _issue_license(self) -> None:
        self.txt_license_key.clear()
        self.lbl_license_status.setText("Issuing license...")
        try:
            api = self._require_api()
        except WorkerApiError as error:
            self.lbl_license_status.setText(f"License was not issued: {error}")
            QMessageBox.warning(self, "Unable to issue license", str(error))
            return

        email = self.txt_license_email.text().strip()
        machine_id = self.txt_license_machine.text().strip()
        days = self.spin_days.value()
        operator = self.txt_operator.text().strip() or "NOC_Operator"

        def on_success(key: object) -> None:
            self.txt_license_key.setText(key)
            self.lbl_license_status.setText("License issued.")
            self._request_after_finished = self._refresh_licenses

        def on_error(message: str) -> None:
            self.txt_license_key.clear()
            self.lbl_license_status.setText(f"License was not issued: {message}")
            QMessageBox.warning(self, "Unable to issue license", message)

        self._run_request(
            lambda: api.issue_license(email, machine_id, days, operator),
            on_success,
            busy_message="Issuing license...",
            on_error=on_error,
        )

    def _copy_license(self) -> None:
        key = self.txt_license_key.text()
        if key and QApplication.clipboard():
            QApplication.clipboard().setText(key)
            self.lbl_license_status.setText("License key copied.")

    def _create_user(self) -> None:
        try:
            api = self._require_api()
        except WorkerApiError as error:
            QMessageBox.warning(self, "Unable to create account", str(error))
            return

        username = self.txt_new_username.text().strip()
        display_name = self.txt_new_display.text().strip()
        password = self.txt_new_password.text()

        def on_success(_result: object) -> None:
            self.txt_new_password.clear()
            self._request_after_finished = self._refresh_users
            QMessageBox.information(
                self,
                "Account created",
                "The operator account was created.",
            )

        self._run_request(
            lambda: api.create_user(username, display_name, password),
            on_success,
            busy_message="Creating operator account...",
            on_error=lambda message: QMessageBox.warning(
                self,
                "Unable to create account",
                message,
            ),
        )

    def _selected_username(self) -> str | None:
        row = self.user_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Select an account",
                "Select an operator account first.",
            )
            return None
        item = self.user_table.item(row, 0)
        return item.text() if item else None

    def _reset_selected_password(self) -> None:
        username = self._selected_username()
        if not username:
            return
        password, accepted = QInputDialog.getText(
            self,
            "Reset password",
            f"New password for {username} (at least 12 characters):",
            QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return

        try:
            api = self._require_api()
        except WorkerApiError as error:
            QMessageBox.warning(self, "Unable to reset password", str(error))
            return

        def on_success(_result: object) -> None:
            QMessageBox.information(
                self,
                "Password reset",
                "The account password was changed.",
            )

        self._run_request(
            lambda: api.reset_password(username, password),
            on_success,
            busy_message="Resetting account password...",
            on_error=lambda message: QMessageBox.warning(
                self,
                "Unable to reset password",
                message,
            ),
        )

    def _toggle_selected_user(self) -> None:
        username = self._selected_username()
        if not username:
            return
        row = self.user_table.currentRow()
        role_item = self.user_table.item(row, 2)
        if role_item is None or role_item.text() != "operator":
            QMessageBox.information(
                self,
                "Account cannot be changed",
                "Only operator accounts can be enabled or disabled.",
            )
            return
        status_item = self.user_table.item(row, 3)
        if status_item is None or status_item.text() not in ("Active", "Inactive"):
            QMessageBox.information(
                self,
                "Account status unavailable",
                "Refresh the account list before changing its status.",
            )
            return
        currently_active = status_item.text() == "Active"
        active = not currently_active
        try:
            api = self._require_api()
        except WorkerApiError as error:
            QMessageBox.warning(self, "Unable to update account status", str(error))
            return

        action = "enable" if active else "disable"
        confirmation = QMessageBox.question(
            self,
            "Confirm account status change",
            f"Are you sure you want to {action} operator account '{username}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return

        def on_success(_result: object) -> None:
            self._request_after_finished = self._refresh_users

        self._run_request(
            lambda: api.set_user_active(username, active),
            on_success,
            busy_message=f"Updating '{username}' account status...",
            on_error=lambda message: QMessageBox.warning(
                self,
                "Unable to update account status",
                message,
            ),
        )

    def _logout(self) -> None:
        api = self._api
        self._api = None
        self.txt_password.clear()
        self.stack.setCurrentIndex(0)
        if api is None:
            return

        self._run_request(
            api.logout,
            lambda _result: None,
            busy_message="Signing out...",
            on_error=lambda message: QMessageBox.warning(
                self,
                "Sign out",
                message,
            ),
        )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NOC Tools Administrator")
    app.setWindowIcon(app_icon(DARK_THEME))
    window = NocToolsAdminWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
