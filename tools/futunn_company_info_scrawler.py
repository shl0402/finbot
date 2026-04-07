from playwright.sync_api import sync_playwright
import json

def scrape_futunn_stock_info(url: str, headless: bool = True) -> dict:
    """
    Scrapes detailed company and stock information from a Futunn stock page.
    
    :param url: The full URL of the Futunn stock company page (e.g., https://www.futunn.com/en/stock/01810-HK/company)
    :param headless: If True, runs the browser invisibly.
    """
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
        
        # Mask the webdriver property to avoid basic bot detection
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = context.new_page()
        
        print(f"Loading Futunn stock page: {url} ...")
        page.goto(url, wait_until="domcontentloaded")
        
        # Wait for the company info section to mount in the DOM
        try:
            page.wait_for_selector('.company-info', timeout=15000)
        except Exception:
            print("Timeout waiting for company info to load.")
            browser.close()
            return {}

        # Extract data using browser-side JavaScript
        stock_data = page.evaluate('''() => {
            const getText = (selector) => {
                const el = document.querySelector(selector);
                return el ? el.innerText.trim() : "N/A";
            };

            const data = {
                company_name: getText('.detail-top-head h2.name'),
                price: "N/A",
                change_price: getText('.price-current .change-price'),
                change_percent: getText('.price-current .change-ratio'),
                description: getText('.company-desc p.text-wrap'),
                market_cap: "N/A",
                pe_ratio: "N/A",
                stats: {},
                profile: {}
            };

            // Clean up the price string (it often contains nested icon text/spacing)
            const priceEl = document.querySelector('.price-current .price');
            if (priceEl) {
                // Grab just the first text node to avoid nested icon text
                data.price = priceEl.childNodes[0].textContent.trim();
            }

            // Extract the Key Stats grid (Market Cap, P/E, Volume, etc.)
            const statItems = document.querySelectorAll('.detail-card .card-item');
            statItems.forEach(item => {
                const spans = item.querySelectorAll('span');
                if (spans.length >= 2) {
                    const val = spans[0].innerText.trim();
                    const key = spans[1].innerText.trim();
                    data.stats[key] = val;
                }
            });

            // Extract the Company Profile list (ISIN, Listing Date, CEO, etc.)
            const profileItems = document.querySelectorAll('.company-info-item');
            profileItems.forEach(item => {
                const titleEl = item.querySelector('.title');
                const valueEl = item.querySelector('.value');
                if (titleEl && valueEl) {
                    const key = titleEl.innerText.trim();
                    const val = valueEl.innerText.trim();
                    data.profile[key] = val;
                }
            });

            // Elevate highly requested stats to the top level for convenience
            if (data.stats['Market Cap']) data.market_cap = data.stats['Market Cap'];
            if (data.stats['P/E (TTM)']) data.pe_ratio = data.stats['P/E (TTM)'];
            else if (data.stats['P/E (Static)']) data.pe_ratio = data.stats['P/E (Static)'];

            return data;
        }''')

        browser.close()
        return stock_data

if __name__ == "__main__":
    test_url = "https://www.futunn.com/en/stock/01810-HK/company"
    result = scrape_futunn_stock_info(test_url, headless=True)
    print(json.dumps(result, indent=4, ensure_ascii=False))