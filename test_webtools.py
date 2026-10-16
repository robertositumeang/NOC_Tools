import time
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient

import desktop_app
from noc_brand import DARK_THEME, LIGHT_THEME, THEMES, theme_stylesheet
from WebTools import main as web_tools_main
from WebTicketChecker import server as ticket_checker_server
from WebTools.server import app


def test_root_redirects_to_dashboard() -> None:
    response = TestClient(app).get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/dashboard/"


def test_dashboard_api_and_static_assets_are_mounted() -> None:
    client = TestClient(app)

    health = client.get("/dashboard/api/health")
    asset = client.get("/dashboard/static/network_bg.svg")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert asset.status_code == 200
    assert "<svg" in asset.text
    assert client.get("/dashboard/api/gaps").status_code == 404


def test_ticket_checker_api_and_static_assets_are_mounted() -> None:
    client = TestClient(app)

    health = client.get("/ticket-checker/api/health")
    asset = client.get("/ticket-checker/static/network_bg.svg")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert asset.status_code == 200
    assert "<svg" in asset.text
    assert client.get("/ticket-checker/api/summary").status_code == 404


def test_shared_theme_stylesheet_uses_solid_card_colors() -> None:
    for theme_name in (DARK_THEME, LIGHT_THEME):
        stylesheet = theme_stylesheet(theme_name)
        card_color = THEMES[theme_name]["card_bg"]
        alternate_color = THEMES[theme_name]["card_alt"]

        assert f"background: {card_color};" in stylesheet
        assert f"background: {alternate_color};" in stylesheet
        assert f"{card_color}E6" not in stylesheet
        assert f"{card_color}EA" not in stylesheet
        assert f"{alternate_color}F5" not in stylesheet


def test_ticket_checker_defaults_apps_script_url_when_unconfigured(monkeypatch) -> None:
    expected_url = (
        "https://script.google.com/macros/s/"
        "AKfycbwTr7k16fRCIe6v6is3EnYXDfiXHaCi-SHKdS4skJ0dBQqqhkCCKiNtyaazhjWLbG6LjQ/exec"
    )
    monkeypatch.setitem(
        ticket_checker_server._state,
        "apps_script_url",
        ticket_checker_server._initial_apps_script_url({}),
    )

    client = TestClient(app)
    settings = client.get("/ticket-checker/api/sheets-settings")
    script = client.get("/ticket-checker/static/app.js").text

    assert ticket_checker_server.DEFAULT_APPS_SCRIPT_URL == expected_url
    assert settings.status_code == 200
    assert settings.json() == {"apps_script_url": expected_url}
    assert 'if (inp && d.apps_script_url) inp.value = d.apps_script_url;' in script


def test_ticket_checker_preserves_saved_apps_script_url(monkeypatch) -> None:
    saved_url = "https://script.google.com/macros/s/custom-deployment/exec"
    monkeypatch.setitem(
        ticket_checker_server._state,
        "apps_script_url",
        ticket_checker_server._initial_apps_script_url(
            {"apps_script_url": saved_url}
        ),
    )

    settings = TestClient(app).get("/ticket-checker/api/sheets-settings")

    assert settings.status_code == 200
    assert settings.json() == {"apps_script_url": saved_url}


def test_ticket_checker_preload_runs_in_combined_lifespan(monkeypatch) -> None:
    calls: list[bool] = []

    class CachedClient:
        def get_tt_data(self, force_refresh: bool = False) -> list[dict[str, str]]:
            calls.append(force_refresh)
            return [{"Ticket ID": "TT-1"}]

    monkeypatch.setattr(ticket_checker_server, "_get_client", CachedClient)

    with TestClient(app) as client:
        deadline = time.monotonic() + 2
        status = client.get("/ticket-checker/api/db-status").json()
        while not status["loaded"] and time.monotonic() < deadline:
            time.sleep(0.01)
            status = client.get("/ticket-checker/api/db-status").json()

    assert calls == [False]
    assert status["loaded"] is True
    assert status["count"] == 1


def test_dashboard_window_opens_before_backend_is_ready(monkeypatch) -> None:
    created_windows: list[dict] = []

    class ImmediateThread:
        def __init__(self, *, target, args, daemon, name) -> None:
            self.target = target
            self.args = args

        def start(self) -> None:
            pass

    webview = Mock()
    webview.create_window.side_effect = lambda **kwargs: created_windows.append(kwargs)
    monkeypatch.setattr("launch_guard.require_launcher_token", lambda _name: None)
    monkeypatch.setattr(web_tools_main, "_parse_args", lambda: SimpleNamespace(page="dashboard"))
    monkeypatch.setattr(web_tools_main, "_find_free_port", lambda: 43210)
    monkeypatch.setattr(web_tools_main.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(
        web_tools_main,
        "_wait_for_server",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Dashboard startup must not block on backend readiness.")
        ),
    )
    monkeypatch.setitem(sys.modules, "webview", webview)

    assert web_tools_main.main() == 0
    assert len(created_windows) == 1
    loading_page = created_windows[0]["html"]
    assert "http://127.0.0.1:43210/dashboard/" in loading_page
    assert 'fetch(target, { mode: "no-cors", cache: "no-store" })' in loading_page
    assert "setTimeout(connect, 100)" in loading_page
    assert "Server belum merespons" in loading_page
    webview.start.assert_called_once()


def test_web_pages_keep_static_assets_and_switch_between_modules() -> None:
    client = TestClient(app)

    dashboard = client.get("/dashboard/")
    checker = client.get("/ticket-checker/")

    assert dashboard.status_code == 200
    assert '/dashboard/static/app.js' in dashboard.text
    assert 'href="/ticket-checker/"' in dashboard.text
    assert checker.status_code == 200
    assert '/ticket-checker/static/app.js' in checker.text
    assert 'href="/dashboard/"' in checker.text


def test_dashboard_csv_actions_explain_export_scope() -> None:
    page = TestClient(app).get("/dashboard/").text

    assert "Ekspor semua tiket (CSV)" in page
    assert "semua tiket yang tersedia di database, tanpa filter daftar" in page
    assert "Ekspor hasil filter (CSV)" in page
    assert "tiket OPEN sesuai filter pencarian, aging, paket, dan provinsi" in page


def test_ticket_checker_upload_controls_are_single_file_and_compact() -> None:
    page = TestClient(app).get("/ticket-checker/").text
    script = TestClient(app).get("/ticket-checker/static/app.js").text

    assert 'id="downInput" accept=".xlsx,.xlsm,.xls"' in page
    assert 'id="unmonInput" accept=".xlsx,.xlsm,.xls"' in page
    assert "Pilih atau seret satu file .xlsx" in page
    assert "min-height:82px" in page
    assert "files.length > 1" in script
    assert "files.length !== 1" in script


def test_ticket_checker_keeps_header_download_action_without_status_duplicate() -> None:
    page = TestClient(app).get("/ticket-checker/").text
    script = TestClient(app).get("/ticket-checker/static/app.js").text

    assert 'onclick="openDownloadsFolder()"' in page
    assert 'class="status-link"' not in page
    assert "!result.ok" in script


def test_ticket_checker_selection_actions_match_frontend_handlers_and_ids() -> None:
    client = TestClient(app)
    page = client.get("/ticket-checker/").text
    script = client.get("/ticket-checker/static/app.js").text

    assert 'id="btnWriteSheets" onclick="openSheetsWriteModal()"' in page
    assert 'id="btnCopyTsv" onclick="copySelectedTsv()"' in page
    assert "function openSheetsWriteModal()" in script
    assert "function copySelectedTsv()" in script
    assert 'document.getElementById("checkAll") || document.getElementById("checkAllGaps")' in script
    assert 'document.getElementById("selectionInfo") || document.getElementById("selInfo")' in script
    assert 'document.getElementById("btnWriteSheets") || document.getElementById("writeToSheetsBtn")' in script
    assert 'document.getElementById("btnCopyTsv") || document.getElementById("copyTsvBtn")' in script
    assert "await copyTextToClipboard(j.tsv || \"\")" in script
    assert "document.execCommand(\"copy\")" in script


def test_ticket_checker_accepts_one_file_and_rejects_multiple_for_each_type(
    monkeypatch,
) -> None:
    for prefix in ("down", "unmon"):
        monkeypatch.setitem(ticket_checker_server._state, f"{prefix}_rows", [])
        monkeypatch.setitem(ticket_checker_server._state, f"{prefix}_filename", "")
        monkeypatch.setitem(ticket_checker_server._state, f"{prefix}_count", 0)
    monkeypatch.setattr(
        ticket_checker_server,
        "read_incident_file",
        lambda _path: [{"Site ID": "ABC00001"}],
    )
    client = TestClient(app)

    for file_type in ("down", "unmon"):
        files = [
            ("files", ("first.xlsx", b"first", "application/octet-stream")),
            ("files", ("second.xlsx", b"second", "application/octet-stream")),
        ]
        rejected = client.post(f"/ticket-checker/api/upload/{file_type}", files=files)
        assert rejected.status_code == 400
        assert "tepat satu file" in rejected.json()["detail"]
        assert ticket_checker_server._state[f"{file_type}_count"] == 0

        accepted = client.post(
            f"/ticket-checker/api/upload/{file_type}",
            files=[
                (
                    "files",
                    (f"{file_type}.xlsx", b"one workbook", "application/octet-stream"),
                )
            ],
        )
        assert accepted.status_code == 200
        assert accepted.json()["ok"] is True
        assert accepted.json()["file_count"] == 1
        assert ticket_checker_server._state[f"{file_type}_count"] == 1


def test_ticket_checker_open_downloads_reports_failures(monkeypatch) -> None:
    def fail_open(*_args, **_kwargs):
        raise OSError("Explorer unavailable")

    monkeypatch.setattr(ticket_checker_server.subprocess, "Popen", fail_open)

    response = TestClient(app).post("/ticket-checker/api/open-downloads")

    assert response.status_code == 200
    assert response.json() == {"ok": False, "error": "Explorer unavailable"}


def test_ticket_checker_open_downloads_opens_folder_from_header_action(
    monkeypatch, tmp_path
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    process = Mock()
    monkeypatch.setattr(ticket_checker_server.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(ticket_checker_server.subprocess, "Popen", process)

    response = TestClient(app).post("/ticket-checker/api/open-downloads")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "path": str(downloads)}
    process.assert_called_once_with(["explorer.exe", str(downloads)])


def test_dashboard_frontend_links_to_ticket_checker_in_same_host() -> None:
    client = TestClient(app)

    response = client.post("/dashboard/api/open-ticket-checker")

    assert response.status_code == 200
    assert response.json() == {"success": True, "url": "/ticket-checker/"}


def test_dashboard_launcher_starts_shared_web_tools_with_dashboard_page(monkeypatch) -> None:
    commands: list[tuple[list[str], dict]] = []
    process = Mock()

    def fake_popen(command: list[str], **kwargs) -> None:
        commands.append((command, kwargs))
        return process

    monkeypatch.setattr(desktop_app, "generate_launch_token", lambda: "launch-token")
    monkeypatch.setattr(desktop_app.subprocess, "Popen", fake_popen)

    assert desktop_app.launch_subprocess_app("dashboard") is True

    command, options = commands[0]
    assert command[-2:] == ["--page", "dashboard"]
    launcher = Path(command[1] if command[0] == desktop_app.sys.executable else command[0])
    assert launcher.name in {"main.py", "NOC Web Tools.exe"}
    assert options["env"]["NOC_LAUNCH_TOKEN"] == "launch-token"
    process.wait.assert_called_once_with()


def test_ticket_checker_launcher_starts_shared_web_tools_with_checker_page(monkeypatch) -> None:
    commands: list[tuple[list[str], dict]] = []
    process = Mock()

    def fake_popen(command: list[str], **kwargs) -> None:
        commands.append((command, kwargs))
        return process

    monkeypatch.setattr(desktop_app, "generate_launch_token", lambda: "launch-token")
    monkeypatch.setattr(desktop_app.subprocess, "Popen", fake_popen)

    assert desktop_app.launch_subprocess_app("ticket_checker") is True

    command, options = commands[0]
    assert command[-2:] == ["--page", "ticket-checker"]
    launcher = Path(command[1] if command[0] == desktop_app.sys.executable else command[0])
    assert launcher.name in {"main.py", "NOC Web Tools.exe"}
    assert options["env"]["NOC_LAUNCH_TOKEN"] == "launch-token"
    process.wait.assert_called_once_with()


def test_capture_modem_launcher_starts_packaged_executable(monkeypatch) -> None:
    commands: list[tuple[list[str], dict]] = []
    process = Mock()

    def fake_exists(path: Path) -> bool:
        return path.name == "Capture_Modem.exe" and path.parent.name == "bin"

    def fake_popen(command: list[str], **kwargs) -> None:
        commands.append((command, kwargs))
        return process

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(desktop_app, "generate_launch_token", lambda: "launch-token")
    monkeypatch.setattr(desktop_app.subprocess, "Popen", fake_popen)

    assert desktop_app.launch_subprocess_app("modem") is True

    command, options = commands[0]
    executable = Path(command[0])
    assert executable.name == "Capture_Modem.exe"
    assert executable.parent.name == "bin"
    assert options["cwd"] == str(executable.parent)
    assert options["env"]["NOC_LAUNCH_TOKEN"] == "launch-token"
    process.wait.assert_called_once_with()


def test_removed_vpn_workspace_is_not_launchable(monkeypatch) -> None:
    process = Mock()
    monkeypatch.setattr(desktop_app, "generate_launch_token", lambda: "launch-token")
    monkeypatch.setattr(desktop_app.subprocess, "Popen", process)

    assert desktop_app.launch_subprocess_app("vpn") is False
    process.assert_not_called()
