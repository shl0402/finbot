from playwright.sync_api import sync_playwright
import json

def get_stat_value(page, label_text: str) -> str:
    """Helper to extract a value based on its adjacent label text."""
    locator = page.locator(f'div[class*="block-"]:has-text("{label_text}") div[class*="value-"]')
    if locator.count() > 0:
        return locator.first.inner_text().strip()
    return "N/A"

def get_speedometer_rating(page, container_name: str) -> str:
    """Helper to extract rating from TradingView speedometer widgets (Technicals & Analysts)."""
    locator = page.locator(f'[data-container-name="{container_name}"] div:has(> span[class*="speedometerText"])').first
    if locator.count() > 0:
        class_name = locator.get_attribute("class") or ""
        if "strong-buy" in class_name: return "Strong Buy"
        if "strong-sell" in class_name: return "Strong Sell"
        if "buy" in class_name: return "Buy"
        if "sell" in class_name: return "Sell"
        if "neutral" in class_name: return "Neutral"
    return "N/A"

def scrape_tradingview_stock(exchange: str, ticker: str) -> dict:
    base_url = "https://www.tradingview.com"
    url = f"{base_url}/symbols/{exchange}-{ticker}/"
    
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        print(f"Loading {url}...")
        page.goto(url, wait_until="domcontentloaded")
        
        page.wait_for_selector('.js-symbol-last', timeout=10000)

        show_more_btn = page.locator('button[class*="toggleDescriptionButton-"]')
        if show_more_btn.is_visible():
            show_more_btn.click()
            page.wait_for_timeout(500)

        data = {
            "symbol": f"{exchange}:{ticker}",
            "name": page.locator('h1[class*="title-"]').first.inner_text().strip() if page.locator('h1[class*="title-"]').count() > 0 else "N/A",
            "price": {
                "current": page.locator('.js-symbol-last').first.inner_text().strip(),
                "currency": page.locator('.js-symbol-currency').first.inner_text().strip() if page.locator('.js-symbol-currency').count() > 0 else "N/A",
                "change_percent": page.locator('.js-symbol-change-pt').first.inner_text().strip() if page.locator('.js-symbol-change-pt').count() > 0 else "N/A"
            },
            "upcoming_earnings": {
                "next_report_date": get_stat_value(page, "Next report date"),
                "report_period": get_stat_value(page, "Report period"),
                "eps_estimate": get_stat_value(page, "EPS estimate"),
                "revenue_estimate": get_stat_value(page, "Revenue estimate")
            },
            "key_stats": {
                "market_cap": get_stat_value(page, "Market capitalization"),
                "dividend_yield": get_stat_value(page, "Dividend yield (indicated)"),
                "pe_ratio": get_stat_value(page, "Price to earnings Ratio (TTM)"),
                "basic_eps": get_stat_value(page, "Basic EPS (TTM)"),
                "net_income_fy": get_stat_value(page, "Net income (FY)"),
                "revenue_fy": get_stat_value(page, "Revenue (FY)"),
                "shares_float": get_stat_value(page, "Shares float"),
                "beta_1y": get_stat_value(page, "Beta (1Y)")
            },
            "employees": {
                "total": get_stat_value(page, "Employees (FY)"),
                "change_1y": get_stat_value(page, "Change (1Y)"),
                "revenue_per_employee": get_stat_value(page, "Revenue / Employee (1Y)"),
                "net_income_per_employee": get_stat_value(page, "Net income / Employee (1Y)")
            },
            "about": {
                "sector": get_stat_value(page, "Sector"),
                "industry": get_stat_value(page, "Industry"),
                "ceo": get_stat_value(page, "CEO"),
                "headquarters": get_stat_value(page, "Headquarters"),
                "founded": get_stat_value(page, "Founded"),
                "ipo_date": get_stat_value(page, "IPO date"),
                "website": get_stat_value(page, "Website"),
                "description": "N/A"
            },
            "news_headlines": [],
            "technical_analysis": get_speedometer_rating(page, "technicals"),
            "analyst_rating": get_speedometer_rating(page, "widget-analyst-id"),
            "related_stocks": [],
            "etf_ownership": []
        }

        # Extract Description text
        desc_locator = page.locator('div[class*="blockText-"] > div[class*="content-"]')
        if desc_locator.count() > 0:
            data["about"]["description"] = desc_locator.first.inner_text().strip()

        # Extract News Titles and Links
        news_items = []
        news_cards = page.locator('a:has([data-qa-id="news-headline-title"])')
        for i in range(news_cards.count()):
            card = news_cards.nth(i)
            href = card.get_attribute("href")
            # Ensure the link is absolute
            full_link = f"{base_url}{href}" if href and href.startswith('/') else href
            
            title_loc = card.locator('[data-qa-id="news-headline-title"]')
            title = title_loc.inner_text().strip() if title_loc.count() > 0 else "N/A"
            
            if title != "N/A":
                news_items.append({
                    "title": title,
                    "link": full_link or "N/A"
                })
        data["news_headlines"] = news_items

        # Extract Related Stocks
        related_locators = page.locator('[data-container-name="related-symbols"] span[class*="title-dkZGhsyD"]')
        data["related_stocks"] = [loc.inner_text().strip() for loc in related_locators.all() if loc.inner_text().strip()]

        # Extract ETF Ownership (Top holdings)
        etf_locators = page.locator('[data-container-name="etf-ownership"] span[class*="title-dkZGhsyD"]')
        data["etf_ownership"] = [loc.inner_text().strip() for loc in etf_locators.all() if loc.inner_text().strip()]

        browser.close()
        return data

if __name__ == "__main__":
    result = scrape_tradingview_stock("HKEX", "700")
    print(json.dumps(result, indent=4, ensure_ascii=False))