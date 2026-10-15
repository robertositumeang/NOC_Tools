import asyncio
from playwright.async_api import async_playwright

async def capture():
    print("[*] Launching browser for capture test...", flush=True)
    async with async_playwright() as p:
        # Launch using installed Chrome or Edge
        browser = await p.chromium.launch(
            headless=True,
            channel="msedge" # Using Windows built-in Edge
        )
        context = await browser.new_context(
            http_credentials={
                "username": "comtech",
                "password": "comtech"
            },
            viewport={"width": 1366, "height": 768}
        )
        page = await context.new_page()
        
        print("[*] Navigating to http://10.70.1.225/ ...", flush=True)
        response = await page.goto("http://10.70.1.225/", timeout=15000)
        print(f"[*] Response status: {response.status}", flush=True)
        
        # Wait for network or frames to load
        await page.wait_for_timeout(3000)
        
        screenshot_path = "capture_test.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"[+] Screenshot saved to {screenshot_path}", flush=True)
        
        title = await page.title()
        print(f"[+] Page title: {title}", flush=True)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(capture())
