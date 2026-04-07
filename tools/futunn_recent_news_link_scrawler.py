from playwright.sync_api import sync_playwright
import json

def scrape_futunn_stock_news(url: str, headless: bool = True) -> list:
    """
    Scrapes the most recent 20 news items for a given Futunn stock.
    
    :param url: The full URL of the Futunn stock news page (e.g., https://www.futunn.com/en/stock/01810-HK/news)
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
        print(f"Loading Futunn news page: {url} ...")
        page.goto(url, wait_until="domcontentloaded")
        
        # Wait for the first batch of news items to load
        try:
            page.wait_for_selector('ul.news-box li.news-item', timeout=15000)
        except Exception:
            print("Timeout waiting for news items to load.")
            browser.close()
            return []

        # Attempt to click "Load More" if we have fewer than 20 items
        # Limit to a few retries to prevent infinite loops
        for _ in range(5):
            if page.locator('ul.news-box li.news-item').count() >= 20:
                break
                
            load_more_btn = page.locator('.add-more-news')
            if load_more_btn.is_visible():
                load_more_btn.click()
                page.wait_for_timeout(1500)  # Wait for the new items to populate
            else:
                break

        # Extract data using browser-side JavaScript for max reliability
        news_data = page.evaluate('''() => {
            const items = document.querySelectorAll('ul.news-box li.news-item');
            const data = [];
            
            // Loop up to 20 items
            for (let i = 0; i < items.length && i < 20; i++) {
                const item = items[i];
                
                const linkEl = item.querySelector('a');
                const titleEl = item.querySelector('.news-title');
                const descEl = item.querySelector('.news-des');
                
                let sourceText = "N/A";
                let timeText = "N/A";
                
                // The source and time are mapped in spans inside .news-meta
                const metaSpans = item.querySelectorAll('.news-meta span.ellipsis');
                metaSpans.forEach(span => {
                    if (span.classList.contains('news-source')) {
                        sourceText = span.textContent.trim();
                    } else {
                        // The time span does not contain 'news-source'
                        timeText = span.textContent.trim();
                    }
                });

                let href = linkEl ? linkEl.getAttribute('href') : "N/A";
                // Ensure relative URLs are converted to absolute
                if (href !== "N/A" && href.startsWith('/')) {
                    href = "https://www.futunn.com" + href;
                }

                data.push({
                    title: titleEl ? titleEl.textContent.trim() : "N/A",
                    link: href,
                    time: timeText,
                    source: sourceText,
                    short_description: descEl ? descEl.textContent.trim() : "N/A"
                });
            }
            
            return data;
        }''')

        browser.close()
        return news_data

if __name__ == "__main__":
    test_url = "https://www.futunn.com/en/stock/01810-HK/news"
    result = scrape_futunn_stock_news(test_url, headless=True)
    print(json.dumps(result, indent=4, ensure_ascii=False))