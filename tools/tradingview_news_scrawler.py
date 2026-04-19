# NOT READY YET (Trading View only allow login users to view news content, so we need to implement login first)

from playwright.sync_api import sync_playwright
import json

def scrape_tradingview_news(url: str, headless: bool = True) -> dict:
    base_url = "https://www.tradingview.com"
    
    with sync_playwright() as p:
        browser = p.firefox.launch(
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
        
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = context.new_page()
        print(f"Loading news article: {url} ...")
        page.goto(url, wait_until="domcontentloaded")
        
        try:
            page.wait_for_selector('h1[data-qa-id="news-description-title"]', timeout=15000)
        except Exception:
            print("Timeout waiting for news article to load.")
            browser.close()
            return {}

        try:
            page.wait_for_selector('div[data-qa-id="news-story-content"]', timeout=8000)
        except Exception:
            pass

        news_data = page.evaluate(r'''() => {
            const data = {
                title: "N/A",
                timestamp: "N/A",
                content: [],
                related_stocks: []
            };

            const titleEl = document.querySelector('h1[data-qa-id="news-description-title"]');
            if (titleEl) data.title = titleEl.textContent.trim();

            const timeEl = document.querySelector('time[datetime]');
            if (timeEl) data.timestamp = timeEl.getAttribute('datetime');

            const storyRoot = document.querySelector('div[data-qa-id="news-story-content"]');

            // Extract article paragraphs from the main story body only.
            const bodyCandidates = [
                storyRoot?.querySelector('div[class*="body-"]'),
                storyRoot?.querySelector('div[class*="content-"]'),
                document.querySelector('main p')?.closest('article')
            ].filter(Boolean);

            for (const bodyEl of bodyCandidates) {
                const paragraphs = bodyEl.querySelectorAll('p');
                paragraphs.forEach(p => {
                    const text = p.textContent.trim();
                    if (text) data.content.push(text);
                });
                if (data.content.length > 0) break;
            }

            if (data.content.length === 0) {
                const articleText = storyRoot?.querySelector('article')?.innerText || "";
                const lines = articleText
                    .split(/\n+/)
                    .map(line => line.trim())
                    .filter(Boolean);

                const noise = [
                    /^news$/i,
                    /^reuters$/i,
                    /^refinitiv$/i,
                    /^\d+\s+min\s+read$/i,
                    /^compare charts$/i,
                    /^analyze on supercharts$/i,
                    /^latest news$/i,
                    /^more news from/i,
                    /^show more$/i,
                    /^copyright/i
                ];

                lines.forEach(line => {
                    if (line === data.title) return;
                    if (noise.some(rx => rx.test(line))) return;
                    if (line.startsWith('©')) return;
                    if (line.length < 60) return;
                    data.content.push(line);
                });
            }

            if (data.content.length === 0) {
                const ldScripts = document.querySelectorAll('script[type="application/ld+json"]');
                ldScripts.forEach(script => {
                    try {
                        const json = JSON.parse(script.textContent || "{}");
                        const queue = [json];
                        while (queue.length > 0) {
                            const item = queue.shift();
                            if (!item || typeof item !== 'object') continue;
                            if (typeof item.articleBody === 'string' && item.articleBody.trim()) {
                                data.content.push(item.articleBody.trim());
                            }
                            if (typeof item.description === 'string' && item.description.trim()) {
                                data.content.push(item.description.trim());
                            }
                            Object.values(item).forEach(value => {
                                if (value && typeof value === 'object') queue.push(value);
                            });
                        }
                    } catch (e) {
                        // Ignore malformed ld+json blocks.
                    }
                });
            }

            if (data.content.length === 0) {
                const metaDescription =
                    document.querySelector('meta[property="og:description"]')?.getAttribute('content') ||
                    document.querySelector('meta[name="description"]')?.getAttribute('content');
                if (metaDescription && metaDescription.trim()) {
                    data.content.push(metaDescription.trim());
                }
            }

            data.content = Array.from(new Set(data.content));

            // Extract symbol chips (ticker + % move) shown above the article body.
            let stockTags = storyRoot?.querySelectorAll('div[class*="symbolsContainer-"] a[role="tab"]') || [];
            if (stockTags.length === 0) {
                stockTags = document.querySelectorAll('a[role="tab"][href*="/symbols/"]');
            }

            stockTags.forEach(tag => {
                const descEl = tag.querySelector('span[class*="description-"]') || tag.querySelector('span[class*="text-"]');
                const percentEl = tag.querySelector(
                    'span[class*="positivePercent-"], span[class*="negativePercent-"], span[class*="neutralPercent-"]'
                );
                
                if (descEl) {
                    let changePercent = percentEl ? percentEl.textContent.trim() : "";
                    if (!changePercent) {
                        const match = (tag.textContent || '').match(/[+\-−]\d+(?:\.\d+)?%/);
                        if (match) changePercent = match[0];
                    }

                    data.related_stocks.push({
                        ticker: descEl.textContent.trim(),
                        change_percent: changePercent || "N/A"
                    });
                }
            });

            return data;
        }''')

        browser.close()
        
        # Post-processing: Format unicode minus signs
        for stock in news_data.get("related_stocks", []):
            if stock["change_percent"]:
                stock["change_percent"] = stock["change_percent"].replace('−', '-')
            
        # Deduplicate stocks safely
        seen = set()
        unique_stocks = []
        for stock in news_data["related_stocks"]:
            if stock["ticker"] not in seen:
                seen.add(stock["ticker"])
                unique_stocks.append(stock)
                
        news_data["related_stocks"] = unique_stocks

        return news_data

if __name__ == "__main__":
    test_url = "https://www.tradingview.com/news/DJN_DN20260407001616:0/"
    result = scrape_tradingview_news(test_url, headless=True)
    print(json.dumps(result, indent=4, ensure_ascii=False))