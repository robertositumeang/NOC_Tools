import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel='msedge')
        context = await browser.new_context(
            http_credentials={'username': 'comtech', 'password': 'comtech'},
            viewport={'width': 1100, 'height': 800}
        )
        page = await context.new_page()
        # Open main frame
        await page.goto('http://10.70.1.225/', wait_until='domcontentloaded')
        await page.wait_for_timeout(2000)
        
        # Change main_content iframe to commission.htm (as in user's sample!)
        await page.evaluate("""
            const iframe = document.getElementById('main_content');
            if (iframe) {
                iframe.src = 'commission.htm';
            }
        """)
        await page.wait_for_timeout(3000)
        
        # Adjust iframe height so nothing is truncated
        await page.evaluate("""
            const iframe = document.getElementById('main_content');
            if (iframe) {
                try {
                    const doc = iframe.contentDocument || iframe.contentWindow.document;
                    if (doc && doc.body) {
                        iframe.style.height = (doc.body.scrollHeight + 50) + 'px';
                    }
                } catch(e) {}
            }
        """)
        await page.wait_for_timeout(500)
        
        # Take full page screenshot
        await page.screenshot(path='test_composite.png', full_page=True)
        await browser.close()
        print('Captured test_composite.png!')

if __name__ == "__main__":
    asyncio.run(test())
