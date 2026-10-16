"""
WebTicketChecker – main entry point.
Starts uvicorn (FastAPI) on a free port, then launches pywebview window
using the Edge WebView2 backend (pre-installed on Windows 10/11).
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

# In PyInstaller windowed mode (console=False), sys.stdout and sys.stderr are None.
# Provide dummy streams so libraries (uvicorn, logging) don't crash on isatty / write.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# ── Path bootstrap (works both dev and PyInstaller frozen) ──────────
if getattr(sys, "frozen", False):
    ROOT = Path(sys._MEIPASS)  # type: ignore[attr-defined]
else:
    ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Security: only allow launch from NOC Tools.exe (after login) ────
from launch_guard import require_launcher_token  # noqa: E402
require_launcher_token("NOC Web Ticket Checker")

_startup_error: str | None = None


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, timeout: float = 15.0) -> bool:
    """Poll localhost until the server accepts connections or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return True
        except OSError:
            time.sleep(0.03)
    return False


def _start_server(port: int) -> None:
    global _startup_error
    try:
        import uvicorn
        from WebTicketChecker.server import app  # noqa: PLC0415

        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_config=None,  # Disable uvicorn log dictConfig (avoids isatty on None stdout)
            access_log=False,
        )
        server = uvicorn.Server(config)
        server.run()
    except Exception:
        import traceback
        _startup_error = traceback.format_exc()
        try:
            log_p = Path.home() / ".noc_cache" / "ticket_checker_server.log"
            log_p.parent.mkdir(parents=True, exist_ok=True)
            log_p.write_text(_startup_error, encoding="utf-8")
        except Exception:
            pass


def main() -> None:
    port = _find_free_port()

    server_thread = threading.Thread(
        target=_start_server,
        args=(port,),
        daemon=True,
        name="uvicorn-ticketchecker",
    )
    server_thread.start()

    # Wait until the server is actually accepting connections
    ready = _wait_for_server(port, timeout=15.0)

    import webview  # noqa: PLC0415

    if not ready and _startup_error:
        webview.create_window(
            title="NOC Command Center – Error",
            html=(
                "<html><body style='background:#091526;color:#f43f5e;font-family:sans-serif;padding:30px;'>"
                "<h2>Gagal Memulai Backend Server</h2>"
                "<pre style='background:#10213A;padding:15px;border-radius:8px;color:#EEF5FF;overflow:auto;font-size:12px;'>"
                f"{_startup_error}</pre></body></html>"
            ),
            width=900,
            height=600,
        )
    else:
        url = f"http://127.0.0.1:{port}"
        webview.create_window(
            title="NOC Command Center – Ticket Checker",
            url=url,
            width=1280,
            height=800,
            min_size=(1024, 600),
            resizable=True,
            maximized=True,
            text_select=False,
        )

    icon_path = ROOT / "app_icon.ico"
    if not icon_path.exists():
        icon_path = Path(__file__).resolve().parent / "static" / "app_icon.ico"
    icon_arg = str(icon_path) if icon_path.exists() else None

    webview.start(
        gui="edgechromium",   # Edge WebView2 — pre-installed on Win10/11
        debug=False,
        icon=icon_arg,
    )


if __name__ == "__main__":
    main()
