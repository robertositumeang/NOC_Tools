from __future__ import annotations

import argparse
import html
import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

if getattr(sys, "frozen", False):
    ROOT = Path(sys._MEIPASS)  # type: ignore[attr-defined]
else:
    ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_startup_error: str | None = None
_startup_error_lock = threading.Lock()


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_server(port: int) -> None:
    global _startup_error
    try:
        import uvicorn

        from WebTools.server import app

        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_config=None,
            access_log=False,
        )
        uvicorn.Server(config).run()
    except Exception:
        with _startup_error_lock:
            _startup_error = traceback.format_exc()


def _wait_for_server(port: int, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with _startup_error_lock:
            if _startup_error is not None:
                return False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _error_page(message: str) -> str:
    safe_message = html.escape(message)
    return (
        "<html><body style='background:#091526;color:#f43f5e;"
        "font-family:Segoe UI,sans-serif;padding:30px'>"
        "<h2>Gagal Memulai Web Tools</h2>"
        "<pre style='background:#10213A;padding:15px;border-radius:8px;"
        "color:#EEF5FF;overflow:auto;font-size:12px'>"
        f"{safe_message}</pre></body></html>"
    )


def _loading_page(port: int, page: str) -> str:
    page_path = "ticket-checker/" if page == "ticket-checker" else "dashboard/"
    content_url = f"http://127.0.0.1:{port}/{page_path}"
    return f"""<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NOC Tools</title>
  <style>
    body {{ margin:0; min-height:100vh; display:grid; place-items:center;
      background:#091526; color:#eef5ff; font:16px 'Segoe UI',sans-serif; }}
    main {{ text-align:center; }}
    .spinner {{ width:28px; height:28px; margin:0 auto 18px;
      border:3px solid #27415f; border-top-color:#38bdf8;
      border-radius:50%; animation:spin .8s linear infinite; }}
    @keyframes spin {{ to {{ transform:rotate(360deg); }} }}
    #error {{ display:none; color:#fda4af; }}
  </style>
</head>
<body>
  <main>
    <div class="spinner" id="spinner"></div>
    <div id="message">Membuka NOC Tools...</div>
    <div id="error">Server belum merespons. Silakan tutup lalu coba lagi.</div>
  </main>
  <script>
    const target = {content_url!r};
    const startedAt = Date.now();
    function connect() {{
      fetch(target, {{ mode: "no-cors", cache: "no-store" }})
        .then(() => location.replace(target))
        .catch(() => {{
          if (Date.now() - startedAt >= 20000) {{
            document.getElementById("spinner").style.display = "none";
            document.getElementById("message").style.display = "none";
            document.getElementById("error").style.display = "block";
            return;
          }}
          setTimeout(connect, 100);
        }});
    }}
    connect();
  </script>
</body>
</html>"""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NOC Web Tools")
    parser.add_argument(
        "--page",
        choices=("dashboard", "ticket-checker"),
        default="dashboard",
        help="Halaman yang dibuka pertama kali",
    )
    return parser.parse_args()


def main() -> int:
    from launch_guard import require_launcher_token

    require_launcher_token("NOC Web Tools")
    args = _parse_args()
    port = _find_free_port()

    server_thread = threading.Thread(
        target=_start_server,
        args=(port,),
        daemon=True,
        name="uvicorn-noc-web-tools",
    )
    server_thread.start()

    import webview

    webview.create_window(
        title="NOC Command Center",
        html=_loading_page(port, args.page),
        width=1440,
        height=880,
        min_size=(1024, 600),
        resizable=True,
        maximized=True,
        text_select=False,
    )

    icon_path = ROOT / "app_icon.ico"
    icon_arg = str(icon_path) if icon_path.exists() else None
    webview.start(gui="edgechromium", debug=False, icon=icon_arg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
