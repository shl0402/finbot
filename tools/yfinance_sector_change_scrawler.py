from playwright.sync_api import sync_playwright
import json

def scrape_yfinance_sectors(url: str = "https://hk.finance.yahoo.com/sectors/", headless: bool = True) -> list:
    """
    Scrapes the sector names, percentage changes, and links from Yahoo Finance HK.
    
    :param url: The full URL of the Yahoo Finance sectors page.
    :param headless: If True, runs the browser invisibly.
    """
    base_url = "https://hk.finance.yahoo.com"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Mask the webdriver property to avoid detection
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = context.new_page()
        print(f"Loading Yahoo Finance sectors page: {url} ...")
        page.goto(url, wait_until="domcontentloaded")
        
        # Wait for the heatmap containers to load (they hold the reliable link and percentage data)
        try:
            page.wait_for_selector('.rect-container[data-href]', timeout=15000)
        except Exception:
            print("Timeout waiting for sector data to load.")
            browser.close()
            return []

        # Extract data using browser-side JavaScript
        sector_data = page.evaluate(f'''(baseUrl) => {{
            const sectors = [];
            
            // Target the heatmap blocks which contain the name, percentage, and link routing
            const containers = document.querySelectorAll('.rect-container[data-href]');
            
            containers.forEach(container => {{
                const nameEl = container.querySelector('.ticker-div');
                const percentEl = container.querySelector('.percent-div');
                const relativeLink = container.getAttribute('data-href');
                
                if (nameEl && percentEl && relativeLink) {{
                    sectors.push({{
                        sector: nameEl.textContent.trim(),
                        change_percent: percentEl.textContent.trim(),
                        link: baseUrl + relativeLink
                    }});
                }}
            }});
            
            return sectors;
        }}''', base_url)

        browser.close()
        return sector_data

if __name__ == "__main__":
    result = scrape_yfinance_sectors(headless=True)
    print(json.dumps(result, indent=4, ensure_ascii=False))