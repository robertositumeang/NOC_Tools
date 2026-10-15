import asyncio
from playwright.async_api import async_playwright

async def test_smooth():
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
            http_credentials={"username": "comtech", "password": "comtech"},
            viewport={"width": 1050, "height": 800},
            device_scale_factor=1
        )
        page = await context.new_page()
        await page.goto("http://10.70.1.225/", wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)

        # Load commission.htm
        await page.evaluate("""
            () => {
                const frame = document.getElementById('main_content');
                if (frame) {
                    frame.src = 'commission.htm';
                }
            }
        """)
        
        frame_el = await page.wait_for_selector("#main_content")
        c_frame = await frame_el.content_frame()
        if c_frame:
            try:
                await c_frame.wait_for_load_state("domcontentloaded", timeout=12000)
            except:
                pass
        
        await page.wait_for_timeout(2500)
        
        # Injected font refinement: ensure Segoe UI / Arial / Verdana with smooth font antialiasing
        await page.evaluate("""
            () => {
                const style = document.createElement('style');
                style.innerHTML = `
                    * {
                        -webkit-font-smoothing: antialiased !important;
                        -moz-osx-font-smoothing: grayscale !important;
                        text-rendering: optimizeLegibility !important;
                    }
                `;
                document.head.appendChild(style);
                
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
        
        await page.screenshot(path="out_commission_smooth.png", full_page=True)
        await browser.close()
        print("Done smooth screenshot!")

if __name__ == "__main__":
    asyncio.run(test_smooth())
