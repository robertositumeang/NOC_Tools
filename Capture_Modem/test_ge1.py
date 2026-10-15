import asyncio
from playwright.async_api import async_playwright

async def capture_page_with_vfp(page_path, output_name):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel='msedge')
        context = await browser.new_context(
            http_credentials={'username': 'comtech', 'password': 'comtech'},
            viewport={'width': 1050, 'height': 800}
        )
        page = await context.new_page()
        await page.goto('http://10.70.1.225/', wait_until='domcontentloaded')
        await page.wait_for_timeout(1500)
        
        # Inject script to load the subpage into main_content and auto-fit height
        await page.evaluate(f"""
            const iframe = document.getElementById('main_content');
            if (iframe) {{
                iframe.src = '{page_path}';
            }}
        """)
        await page.wait_for_timeout(3000)
        
        # Adjust height so no scrollbars and no cut-off
        await page.evaluate("""
            const iframe = document.getElementById('main_content');
            if (iframe) {
                try {
                    const doc = iframe.contentDocument || iframe.contentWindow.document;
                    if (doc && doc.body) {
                        iframe.style.height = (doc.body.scrollHeight + 40) + 'px';
                    }
                } catch(e) {}
            }
        """)
        await page.wait_for_timeout(500)
        
        await page.screenshot(path=output_name, full_page=True)
        await browser.close()
        print(f"Captured {output_name}")

if __name__ == "__main__":
    asyncio.run(capture_page_with_vfp('ge1.htm', 'test_ge1_composite.png'))
