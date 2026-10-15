import os
import time
import socket
import asyncio
from urllib.parse import urlparse
import requests
from requests.auth import HTTPDigestAuth
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def test_tcp_connection(host: str, port: int = 80, timeout: float = 3.0) -> dict:
    """Test TCP latency to target."""
    start = time.perf_counter()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        latency = (time.perf_counter() - start) * 1000.0
        sock.close()
        if result == 0:
            return {"online": True, "latency_ms": round(latency, 1), "error": None}
        return {"online": False, "latency_ms": None, "error": f"Port {port} closed (errno {result})"}
    except Exception as e:
        return {"online": False, "latency_ms": None, "error": str(e)}

def fetch_telemetry(host: str, username: str = "comtech", password: str = "comtech") -> dict:
    """Fetch live telemetry from vfpHeights.htm."""
    url = f"http://{host}/vfpHeights.htm"
    auth = HTTPDigestAuth(username, password)
    try:
        r = requests.get(url, auth=auth, timeout=6)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}"}
        
        soup = BeautifulSoup(r.text, "html.parser")
        data = {}
        
        # Parse all table cells
        for tr in soup.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            for i in range(len(cells) - 1):
                key = cells[i].upper().replace(":", "").strip()
                val = cells[i+1].strip()
                if key in [
                    "UNIT STATUS", "TRANSMITTER", "RX RF STATUS", "RSL (DBM)",
                    "ES/NO (DB)", "FREQ OFFSET (HZ)", "TX MODCOD", "MAX RX MODCOD",
                    "RX TRAFFIC MODCOD", "MODEM STATE", "WORKING MODE", "TX TRAFFIC",
                    "RX TRAFFIC", "FIRMWARE", "TEST MODE", "STORED EVENT"
                ] and val:
                    data[key] = val

        # Extract unit name if present
        text = soup.get_text()
        if "PAB" in text:
            import re
            m = re.search(r'(PAB[0-9A-Z_]+)', text)
            if m:
                data["UNIT_NAME"] = m.group(1)
                
        return {"success": True, "data": data, "raw_html_len": len(r.text)}
    except Exception as e:
        return {"error": str(e)}

async def _playwright_capture(host: str, page_path: str, username: str, password: str, output_path: str,
                              width: int = 1050, height: int = 800, full_page: bool = True,
                              timeout_ms: int = 25000):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            channel="msedge",
            args=[
                "--enable-font-antialiasing",
                "--font-render-hinting=medium",
                "--force-color-profile=srgb",
                "--disable-lcd-text=false"
            ]
        )
        context = await browser.new_context(
            http_credentials={"username": username, "password": password},
            viewport={"width": width, "height": height},
            device_scale_factor=1
        )
        page = await context.new_page()
        try:
            # Parse clean path if a full URL was supplied
            clean_path = page_path.strip()
            if clean_path.startswith("http://") or clean_path.startswith("https://"):
                parsed = urlparse(clean_path)
                clean_path = parsed.path.lstrip("/")
                if parsed.query:
                    clean_path += f"?{parsed.query}"
            else:
                clean_path = clean_path.lstrip("/")

            # Base URL loads index.html (which contains topFrame with VFP banner and main_content)
            base_url = f"http://{host}/"
            await page.goto(base_url, timeout=timeout_ms, wait_until="domcontentloaded")
            await page.wait_for_timeout(1000)

            if clean_path and clean_path not in ["home.htm", "index.html", "main.htm"]:
                # Switch main_content iframe to target page
                await page.evaluate(f"""
                    () => {{
                        const frame = document.getElementById('main_content');
                        if (frame) {{
                            frame.src = '{clean_path}';
                        }}
                    }}
                """)
                
                # Wait for iframe to load its content
                frame_element = await page.wait_for_selector("#main_content")
                content_frame = await frame_element.content_frame()
                if content_frame:
                    try:
                        await content_frame.wait_for_load_state("domcontentloaded", timeout=12000)
                    except Exception:
                        pass
                
                # Wait for scripts and dynamic components to render
                await page.wait_for_timeout(2500)
            else:
                await page.wait_for_timeout(2000)

            # Apply smooth font rendering and resize iframe dynamically
            await page.evaluate("""
                () => {
                    // Inject font antialiasing in parent
                    const style = document.createElement('style');
                    style.innerHTML = `
                        * {
                            -webkit-font-smoothing: antialiased !important;
                            -moz-osx-font-smoothing: grayscale !important;
                            text-rendering: optimizeLegibility !important;
                        }
                    `;
                    document.head.appendChild(style);

                    // Inject font antialiasing and auto-fit in iframe
                    const iframe = document.getElementById('main_content');
                    if (iframe) {
                        try {
                            const doc = iframe.contentDocument || iframe.contentWindow.document;
                            if (doc && doc.head) {
                                const fstyle = doc.createElement('style');
                                fstyle.innerHTML = `
                                    * {
                                        -webkit-font-smoothing: antialiased !important;
                                        -moz-osx-font-smoothing: grayscale !important;
                                        text-rendering: optimizeLegibility !important;
                                    }
                                `;
                                doc.head.appendChild(fstyle);
                            }
                            if (doc && doc.body) {
                                const h = Math.max(doc.body.scrollHeight, doc.documentElement.scrollHeight);
                                iframe.style.height = (h + 35) + 'px';
                            }
                        } catch(e) {}
                    }
                }
            """)
            await page.wait_for_timeout(500)

            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            await page.screenshot(path=output_path, full_page=full_page)
            title = await page.title()
            return {"success": True, "title": title, "path": output_path}
        finally:
            await browser.close()

def capture_page(host: str, page_path: str, username: str = "comtech", password: str = "comtech",
                 output_path: str = "captures/screenshot.png", width: int = 1050, height: int = 800,
                 full_page: bool = True) -> dict:
    """Synchronous wrapper for Playwright full layout capture with font smoothing."""
    try:
        return asyncio.run(_playwright_capture(host, page_path, username, password, output_path, width, height, full_page))
    except Exception as e:
        return {"success": False, "error": str(e)}


def ping_modem(host: str, port: int = 80, timeout: float = 2.5) -> tuple:
    """Test TCP connection to modem host and return (is_online: bool, latency_str: str)."""
    res = test_tcp_connection(host, port, timeout)
    if res.get("online"):
        return True, f"{res['latency_ms']} ms"
    return False, res.get("error", "Unreachable")
