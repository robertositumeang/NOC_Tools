import asyncio
from playwright.async_api import async_playwright

async def debug_ge1():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel='msedge')
        context = await browser.new_context(
            http_credentials={'username': 'comtech', 'password': 'comtech'},
            viewport={'width': 1050, 'height': 800}
        )
        page = await context.new_page()
        page.on('console', lambda msg: print('PAGE LOG:', msg.text))
        page.on('pageerror', lambda err: print('PAGE ERROR:', err))
        
        # Navigate to index first
        await page.goto('http://10.70.1.225/', wait_until='domcontentloaded')
        await page.wait_for_timeout(1500)
        
        # Click through to ge1.htm or set iframe src
        await page.evaluate("""
            const iframe = document.getElementById('main_content');
            if (iframe) {
                iframe.src = 'ge1.htm';
            }
        """)
        
        # Wait a bit and inspect iframe document body
        await page.wait_for_timeout(3000)
        
        # Check iframe URL and content
        res = await page.evaluate("""
            () => {
                const iframe = document.getElementById('main_content');
                if (!iframe) return 'no iframe';
                try {
                    const doc = iframe.contentDocument || iframe.contentWindow.document;
                    return {
                        src: iframe.src,
                        url: iframe.contentWindow.location.href,
                        bodyLength: doc.body.innerHTML.length,
                        scrollHeight: doc.body.scrollHeight,
                        scrollWidth: doc.body.scrollWidth
                    };
                } catch(e) {
                    return 'error: ' + e.message;
                }
            }
        """)
        print('Iframe status:', res)
        
        await page.screenshot(path='debug_ge1.png', full_page=True)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_ge1())
