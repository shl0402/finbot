from playwright.sync_api import sync_playwright
import json


STATS_KEYS = [
    "Market Cap",
    "P/E (TTM)",
    "P/E (Static)",
    "Volume",
    "Open",
    "Prev Close",
    "Turnover",
    "Turnover Ratio",
    "Shares",
    "52wk High",
    "52wk Low",
    "P/B",
    "Float Cap",
    "Dividend TTM",
    "Div Yield TTM",
    "Dividend LFY",
    "Div Yield  LFY",
    "Shs Float",
    "Historical High",
    "Historical Low",
    "Avg Price",
    "Lot Size",
    "High",
    "Low",
    "Range %",
]

PROFILE_KEYS = [
    "Symbol",
    "Company Name",
    "ISIN",
    "Listing Date",
    "Issue Price",
    "Shares Offered",
    "Founded",
    "Registered Address",
    "Chairman",
    "Secretary",
    "Audit Institution",
    "Company Category",
    "Registered Office",
    "Head Office and Principal Place of Business",
    "Fiscal Year Ends",
    "Employees",
    "Market",
    "Phone",
    "Fax",
    "Email",
    "Website",
    "Business",
]


def _get_text_or_na(page, selector: str) -> str:
    loc = page.locator(selector)
    if loc.count() == 0:
        return "N/A"
    value = loc.first.inner_text().strip()
    return value if value else "N/A"


def _extract_price(page) -> str:
    loc = page.locator('.price-current .price')
    if loc.count() == 0:
        return "N/A"

    # Keep the first visible line and avoid icon glyph text.
    raw = loc.first.inner_text().strip().split('\n')[0].strip()
    return raw if raw else "N/A"


def _collect_stats_map(page) -> dict:
    stats_map = {}
    items = page.locator('.detail-card .card-item')
    for i in range(items.count()):
        item = items.nth(i)
        spans = item.locator('span')
        if spans.count() < 2:
            continue
        value = spans.nth(0).inner_text().strip()
        label = spans.nth(1).inner_text().strip()
        if label:
            stats_map[label] = value or "N/A"
    return stats_map


def _expand_hidden_stats_if_needed(page, stats_map: dict) -> dict:
    # If key hidden-only fields are missing, expand the card and collect again.
    hidden_only_keys = {
        "High",
        "Low",
        "Open",
        "Prev Close",
        "Turnover",
        "Turnover Ratio",
        "P/E (Static)",
        "52wk High",
        "52wk Low",
        "Historical High",
        "Historical Low",
        "Avg Price",
        "Lot Size",
    }

    if hidden_only_keys.issubset(set(stats_map.keys())):
        return stats_map

    toggle = page.locator('.detail-card .right-tip, .detail-card .arrow-double-down')
    if toggle.count() > 0:
        try:
            toggle.first.click(timeout=3000)
            page.wait_for_timeout(400)
        except Exception:
            return stats_map

    expanded_stats_map = _collect_stats_map(page)

    # Merge while preferring non-empty values.
    merged = dict(stats_map)
    for key, value in expanded_stats_map.items():
        if key not in merged or merged[key] in {"", "N/A", "--"}:
            merged[key] = value
    return merged


def _collect_profile_map(page) -> dict:
    profile_map = {}
    items = page.locator('.company-info-item')
    for i in range(items.count()):
        item = items.nth(i)
        title = item.locator('.title')
        value = item.locator('.value')
        if title.count() == 0 or value.count() == 0:
            continue
        key = title.first.inner_text().strip()
        val = value.first.inner_text().strip()
        if key:
            profile_map[key] = val or "N/A"
    return profile_map


def scrape_futunn_stock_info(stock_code: str, headless: bool = True) -> dict:
    """
    Scrapes detailed company and stock information from a Futunn stock page.
    
    :param stock_code: The stock code (e.g., "01810-HK")
    :param headless: If True, runs the browser invisibly.
    """
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
        
        # Mask the webdriver property to avoid basic bot detection
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = context.new_page()
        
        url = f"https://www.futunn.com/en/stock/{stock_code}/company"

        print(f"Loading Futunn company info page: {url} ...")

        page.goto(url, wait_until="domcontentloaded")
        
        # Wait for the company info section to mount in the DOM
        try:
            page.wait_for_selector('.company-info', timeout=15000)
        except Exception:
            browser.close()
            return {}

        stats_map = _collect_stats_map(page)
        stats_map = _expand_hidden_stats_if_needed(page, stats_map)
        profile_map = _collect_profile_map(page)

        stats = {key: stats_map.get(key, "N/A") for key in STATS_KEYS}
        profile = {key: profile_map.get(key, "N/A") for key in PROFILE_KEYS}

        pe_ratio = stats.get("P/E (TTM)", "N/A")
        if pe_ratio == "N/A":
            pe_ratio = stats.get("P/E (Static)", "N/A")

        stock_data = {
            "company_name": _get_text_or_na(page, '.detail-top-head h2.name'),
            "price": _extract_price(page),
            "change_price": _get_text_or_na(page, '.price-current .change-price'),
            "change_percent": _get_text_or_na(page, '.price-current .change-ratio'),
            "description": _get_text_or_na(page, '.company-desc p.text-wrap'),
            "market_cap": stats.get("Market Cap", "N/A"),
            "pe_ratio": pe_ratio,
            "stats": stats,
            "profile": profile,
        }

        browser.close()
        return stock_data

if __name__ == "__main__":
    test_url = "01810-HK"
    result = scrape_futunn_stock_info(test_url, headless=True)
    print(json.dumps(result, indent=4, ensure_ascii=False))