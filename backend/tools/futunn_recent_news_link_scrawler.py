from playwright.sync_api import sync_playwright
import json

def scrape_futunn_stock_news(stock_code: str, num_news: int = 20, headless: bool = True) -> list:
    """
    Scrapes the most recent num_news items for a given Futunn stock.
    
    :param url: The full URL of the Futunn stock news page (e.g., https://www.futunn.com/en/stock/01810-HK/news)
    :param headless: If True, runs the browser invisibly.
    """
    with sync_playwright() as p:
        browser = p.firefox.launch(
            headless=headless,
            args=[]
        )
        
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0"
        )
        
        # Mask the webdriver property to avoid basic bot detection
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = context.new_page()
        url = f"https://www.futunn.com/en/stock/{stock_code}/news"
        print(f"Loading Futunn news page: {url} ...")
        page.goto(url, wait_until="domcontentloaded")
        
        # Wait for the first batch of news items to load
        try:
            page.wait_for_selector('ul.news-box li.news-item', timeout=15000)
        except Exception as e:
            print(f"Timeout waiting for news items to load: {e}")
            browser.close()
            return []

        # Attempt to click "Load More" if we have fewer than num_news items
        # Limit to a few retries to prevent infinite loops
        for i in range(max(5, (num_news // 10) + 2)):
            current_count = page.locator('ul.news-box li.news-item').count()
            print(f"Scroll iteration {i}: found {current_count} items")
            if current_count >= num_news:
                break
                
            load_more_btn = page.locator('.add-more-news')
            # Fallback if no button found or covered by footer is to scroll down
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)
            
            if load_more_btn.is_visible():
                print("Clicking load more...")
                try:
                    load_more_btn.click(force=True)
                except Exception as e:
                    print(f"Failed to click: {e}")
                page.wait_for_timeout(1500)  # Wait for the new items to populate
            else:
                print("Load more button not visible after scroll.")

        # Extract data using browser-side JavaScript for max reliability
        news_data = page.evaluate('''([maxItems]) => {
            const items = document.querySelectorAll('ul.news-box li.news-item');
            const data = [];
            
            // Loop up to maxItems items
            for (let i = 0; i < items.length && i < maxItems; i++) {
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
        }''', [num_news])

        browser.close()
        return news_data

if __name__ == "__main__":
    test_url = "01810-HK"
    result = scrape_futunn_stock_news("01810-HK", num_news=30, headless=True)
    print(json.dumps(result, indent=4, ensure_ascii=False))