from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import json
import re


# Hardcoded metric types allowed in output.
ALLOWED_METRICS = {
    "Key stats": [
        "Total common shares outstanding",
    ],
    "Valuation ratios": [
        "Price to earnings ratio",
        "Price to sales ratio",
        "Price to cash flow ratio",
        "Price to book ratio",
        "Enterprise value",
        "Enterprise value to EBITDA ratio",
    ],
    "Profitability ratios": [
        "Return on assets %",
        "Return on equity %",
        "Return on invested capital %",
        "Gross margin %",
        "Operating margin %",
        "EBITDA margin %",
        "Net margin %",
    ],
    "Liquidity ratios": [
        "Quick ratio",
        "Current ratio",
        "Inventory turnover",
        "Asset turnover",
    ],
    "Solvency ratios": [
        "Debt to assets ratio",
        "Debt to equity ratio",
        "Long term debt to total assets ratio",
        "Long term debt to total equity ratio",
    ],
    "Per share metrics": [
        "Revenue per share",
        "Operating cash flow per share",
        "Free cash flow per share",
        "EBIT per share",
        "EBITDA per share",
        "Book value per share",
        "Total debt per share",
        "Cash per share",
        "Net current asset value per share",
        "Tangible book value per share",
        "Working capital per share",
        "CapEx per share",
    ],
}


def _clean_text(value: str) -> str:
    if not value:
        return ""
    value = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", value)
    value = value.replace("\u202f", " ")
    return " ".join(value.split()).strip()


def _get_period_labels(page) -> list:
    labels = []
    period_cells = page.locator("div.container-OWKkVLyj div.values-AtxjAQkN > div.container-OxVAcLqi")

    for i in range(period_cells.count()):
        cell = period_cells.nth(i)
        main_loc = cell.locator("div.value-OxVAcLqi")
        sub_loc = cell.locator("div.subvalue-OxVAcLqi")

        main = _clean_text(main_loc.first.inner_text()) if main_loc.count() > 0 else ""
        sub = _clean_text(sub_loc.first.inner_text()) if sub_loc.count() > 0 else ""

        if sub:
            labels.append(f"{main} ({sub})")
        else:
            labels.append(main)

    return labels


def _extract_metrics(page) -> list:
    periods = _get_period_labels(page)
    rows = page.locator("div.container-vKM0WfUu > div")

    current_group = "Ungrouped"
    items = []

    for i in range(rows.count()):
        row = rows.nth(i)

        group_title = row.locator("div.groupTitle-C9MdAMrq")
        if group_title.count() > 0:
            current_group = _clean_text(group_title.first.inner_text()) or current_group
            continue

        metric_name = row.get_attribute("data-name")
        if not metric_name:
            continue

        metric_name = _clean_text(metric_name)

        # Enforce hardcoded metric types only.
        allowed_in_group = ALLOWED_METRICS.get(current_group, [])
        if metric_name not in allowed_in_group:
            continue

        value_cells = row.locator("div.values-C9MdAMrq div.container-OxVAcLqi")

        values = []
        for j in range(value_cells.count()):
            cell = value_cells.nth(j)
            value_loc = cell.locator("div.value-OxVAcLqi")
            value_text = _clean_text(value_loc.first.inner_text()) if value_loc.count() > 0 else ""

            # Premium-locked cells render lock icons without text.
            if not value_text and cell.locator("svg").count() > 0:
                value_text = "LOCKED"

            values.append(value_text)

        if len(values) < len(periods):
            values.extend([""] * (len(periods) - len(values)))
        elif len(values) > len(periods):
            values = values[:len(periods)]

        # Remove locked/empty cells from output to keep only usable values.
        filtered_values = {
            periods[k]: values[k]
            for k in range(len(periods))
            if values[k] and values[k] != "LOCKED"
        }

        # Skip metrics that contain no useful data after trimming.
        if not filtered_values:
            continue

        items.append(
            {
                "group": current_group,
                "metric": metric_name,
                "values": filtered_values,
            }
        )

    return items


def _get_selected_period_type(page) -> str:
    selected = page.locator("#financials-page-tabs button[aria-selected='true']")
    if selected.count() == 0:
        return "unknown"

    selected_id = _clean_text(selected.first.get_attribute("id") or "")
    if selected_id == "FQ":
        return "quarterly"
    if selected_id == "FY":
        return "annual"
    return selected_id or "unknown"


def _switch_period(page, tab_id: str) -> None:
    tab = page.locator(f"#financials-page-tabs button#{tab_id}")
    if tab.count() == 0:
        return

    if _clean_text(tab.first.get_attribute("aria-selected") or "") == "true":
        return

    tab.first.click()
    page.wait_for_timeout(1200)


def scrape_tradingview_stock_analysis(exchange: str, ticker: str, headless: bool = True) -> dict:
    """
    Scrape TradingView Financial Statistics & Ratios page.

    Returns a stable schema for LLM/tool usage:
    {
      symbol, company_name, exchange_name, currency,
      source_url,
      statistics: {
        quarterly: [ { group, metric, values{period:value} }, ... ],
        annual: [ { group, metric, values{period:value} }, ... ]
      }
    }
    """
    base_url = "https://www.tradingview.com"
    url = f"{base_url}/symbols/{exchange}-{ticker}/financials-statistics-and-ratios/"

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        )

        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")

        try:
            page.wait_for_selector("div.container-vKM0WfUu", timeout=30000)
        except PlaywrightTimeoutError:
            browser.close()
            return {}

        company_name = _clean_text(page.locator("h2[class*='title-']").first.inner_text()) if page.locator("h2[class*='title-']").count() > 0 else "N/A"
        exchange_name = _clean_text(page.locator("span[class*='provider-']").first.inner_text()) if page.locator("span[class*='provider-']").count() > 0 else "N/A"
        currency = "N/A"
        currency_header = page.locator("div.firstColumn-OWKkVLyj")
        if currency_header.count() > 0:
            text = _clean_text(currency_header.first.inner_text())
            if text.startswith("Currency:"):
                currency = _clean_text(text.replace("Currency:", ""))

        data = {
            "symbol": f"{exchange}:{ticker}",
            "company_name": company_name,
            "exchange_name": exchange_name,
            "currency": currency,
            "source_url": url,
            "statistics": {},
        }

        # Quarterly (default selected on this page)
        current_period = _get_selected_period_type(page)
        data["statistics"][current_period] = _extract_metrics(page)

        # Annual
        _switch_period(page, "FY")
        annual_period = _get_selected_period_type(page)
        data["statistics"][annual_period] = _extract_metrics(page)

        browser.close()
        return data


if __name__ == "__main__":
    # Xiaomi example requested by user.
    # result = scrape_tradingview_stock_analysis("HKEX", "1810", headless=True)
    # result = scrape_tradingview_stock_analysis("SZSE", "002594", headless=True)
    result = scrape_tradingview_stock_analysis("NASDAQ", "TSLA", headless=True)
    print(json.dumps(result, indent=4, ensure_ascii=False))
