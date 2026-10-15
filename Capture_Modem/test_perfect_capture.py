import asyncio
from playwright.async_api import async_playwright

async def test_pages():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel='msedge')
        context = await browser.new_context(
            http_credentials={'username': 'comtech', 'password': 'comtech'},
            viewport={'width': 1050, 'height': 800}
        )
        
        pages_to_test = [
            ('dpc.htm', 'out_dpc.png'),
            ('commission.htm', 'out_commission.png'),
            ('ge1.htm', 'out_ge1.png'),
            ('mod.htm', 'out_mod.png')
        ]
        
        for path, out_img in pages_to_test:
            page = await context.new_page()
            # Navigate to base page
            await page.goto('http://10.70.1.225/', wait_until='domcontentloaded')
            await page.wait_for_timeout(1000)
            
            # Set iframe source
            await page.evaluate(f"""
                () => {{
                    const frame = document.getElementById('main_content');
                    if (frame) {{
                        frame.src = '{path}';
                    }}
                }}
            """)
            
            # Wait for frame to load its document
            frame_element = await page.wait_for_selector('#main_content')
            content_frame = await frame_element.content_frame()
            
            if content_frame:
                try:
                    await content_frame.wait_for_load_state('domcontentloaded', timeout=10000)
                except Exception as e:
                    print(f"Wait load state error {path}: {e}")
            
            # Wait an additional 2.5s for scripts/dojo/styles to settle
            await page.wait_for_timeout(2500)
            
            # Adjust iframe height to match content
            await page.evaluate("""
                () => {
                    const iframe = document.getElementById('main_content');
                    if (iframe) {
                        try {
                            const doc = iframe.contentDocument || iframe.contentWindow.document;
                            if (doc && doc.body) {
                                const h = Math.max(doc.body.scrollHeight, doc.documentElement.scrollHeight);
                                iframe.style.height = (h + 30) + 'px';
                            }
                        } catch(e) {}
                    }
                }
            """)
            await page.wait_for_timeout(500)
            
            # Take full page screenshot
            await page.screenshot(path=out_img, full_page=True)
            print(f"Successfully captured {out_img}")
            await page.close()
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_pages())
