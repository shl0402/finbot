"""
Futunn news scraper that fetches news spanning the last N calendar days.
Adapts the proven scroll-to-bottom + Load More cycle from
futunn_recent_news_link_scraper.py, but stops based on date (not item count),
then trims to max_per_day per day at the end.
"""

from playwright.sync_api import sync_playwright
import dateparser
import re
from datetime import datetime, timedelta
import json


def scrape_futunn_recent_days_news(
    stock_code: str,
    num_days: int = 30,
    max_per_day: int = 3,
    headless: bool = True,
) -> list:
    """
    Scrape news for a Futunn stock covering the last `num_days` calendar days.

    Args:
        stock_code: Futunn stock code (e.g. "01810-HK", "TSLA-US").
        num_days: Number of past calendar days to cover (default 30).
        max_per_day: Maximum number of news items to return per calendar day (default 3).
        headless: Run browser invisibly.

    Returns:
        List of dicts with keys: title, link, time, source,
        short_description, parsed_date, parsed_date_str.
        Sorted newest-first, capped at max_per_day per day.
    """
    cutoff_date = datetime.now() - timedelta(days=num_days)

    with sync_playwright() as p:
        browser = p.firefox.launch(
            headless=headless,
            args=[],
        )

        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = context.new_page()
        url = f"https://www.futunn.com/en/stock/{stock_code}/news"
        print(f"Loading Futunn news page: {url} ...")
        page.goto(url, wait_until="domcontentloaded")

        try:
            page.wait_for_selector("ul.news-box li.news-item", timeout=15000)
        except Exception as e:
            print(f"Timeout waiting for news items: {e}")
            browser.close()
            return []

        # --- Scroll loop ---
        #
        # Pattern from the proven reference:
        #   1. window.scrollTo(0, document.body.scrollHeight) → scroll page to bottom
        #   2. page.wait_for_timeout(1000)                  → let page settle
        #   3. If Load More button visible → click it, wait 1500ms
        #   4. If button NOT visible → scroll the last news item into view
        #      (triggers lazy loading of older news), wait 1500ms
        #   5. Check oldest date; stop when it passes the cutoff
        #
        # The Load More button only appears once. After that, we rely on
        # scroll-into-view of the last item to trigger lazy loading.
        iterations = 0
        max_iterations = 500
        reached_cutoff = False

        print(f"\nLoading news (cutoff: {cutoff_date.date()}, max_per_day={max_per_day})...")

        while iterations < max_iterations and not reached_cutoff:
            iterations += 1

            # Scroll page to bottom
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)

            load_more_btn = page.locator("button.add-more-news")

            if load_more_btn.is_visible():
                try:
                    load_more_btn.click(force=True)
                    page.wait_for_timeout(1500)
                except Exception as e:
                    print(f"[Iter {iterations}] Failed to click Load More: {e}")
                    break
            else:
                items = page.locator("ul.news-box li.news-item")
                count = items.count()
                if count > 0:
                    try:
                        items.nth(count - 1).scroll_into_view_if_needed()
                    except Exception:
                        pass
                    page.wait_for_timeout(1500)
                else:
                    page.wait_for_timeout(1500)

            # Single bounds check per iteration — print newest → oldest dates
            newest_dt, oldest_dt, newest_raw, oldest_raw = _get_bounds(page)
            if newest_dt and oldest_dt:
                print(f"[Iter {iterations}] {newest_dt.strftime('%Y-%m-%d')} → {oldest_dt.strftime('%Y-%m-%d')}  ({page.locator('ul.news-box li.news-item').count()} items)")
                if oldest_dt < cutoff_date:
                    print(f"[Iter {iterations}] Oldest ({oldest_dt.strftime('%Y-%m-%d')}) < cutoff ({cutoff_date.strftime('%Y-%m-%d')}). Stopping.")
                    reached_cutoff = True
            else:
                print(f"[Iter {iterations}] Could not parse dates  newest={repr(newest_raw)}  oldest={repr(oldest_raw)}")

        final_count = page.locator("ul.news-box li.news-item").count()
        oldest_final, _, _, _ = _get_bounds(page)
        print(f"Scroll loop done after {iterations} iterations. {final_count} items in DOM, oldest: {oldest_final.strftime('%Y-%m-%d') if oldest_final else 'unknown'}")

        # --- Extract all items from DOM ---
        news_data = page.evaluate(
            """([maxItems]) => {
                const items = document.querySelectorAll('ul.news-box li.news-item');
                const data = [];
                for (let i = 0; i < items.length; i++) {
                    const item = items[i];
                    const linkEl = item.querySelector('a');
                    const titleEl = item.querySelector('.news-title');
                    const descEl = item.querySelector('.news-des');
                    let sourceText = "N/A";
                    let timeText = "N/A";
                    const metaSpans = item.querySelectorAll('.news-meta span.ellipsis');
                    metaSpans.forEach(span => {
                        if (span.classList.contains('news-source')) {
                            sourceText = span.textContent.trim();
                        } else if (span.classList.contains('news-time')) {
                            timeText = span.textContent.trim();
                        } else if (!timeText || timeText === "N/A") {
                            timeText = span.textContent.trim();
                        }
                    });
                    let href = linkEl ? linkEl.getAttribute('href') : "N/A";
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
            }""",
            [999999],
        )

        browser.close()

        # --- Filter to date window and group by day ---
        day_groups: dict = {}
        for item in news_data:
            parsed = _parse_date_flexible(item["time"])
            if parsed is None:
                print(f"  [WARN] Could not parse date: {repr(item['time'])} | {item['title'][:40]}")
                continue
            if parsed < cutoff_date:
                continue

            item_date = parsed.date()
            if item_date not in day_groups:
                day_groups[item_date] = []
            day_groups[item_date].append(item)

        # --- Apply max_per_day cap ---
        result = []
        for date_val in sorted(day_groups.keys(), reverse=True):
            result.extend(day_groups[date_val][:max_per_day])

        # Attach parsed_date fields
        for item in result:
            p = _parse_date_flexible(item["time"])
            if p:
                item["parsed_date"] = p
                item["parsed_date_str"] = p.strftime("%Y-%m-%d %H:%M")
            else:
                item["parsed_date"] = None
                item["parsed_date_str"] = item["time"]

        # --- Summary ---
        covered_dates = sorted(day_groups.keys(), reverse=True)
        if covered_dates:
            print(f"  Total DOM items: {len(news_data)}")
            print(f"  Within cutoff: {sum(len(v) for v in day_groups.values())} items")
            print(f"  After max_per_day cap: {len(result)} items across "
                  f"{len(covered_dates)} days ({covered_dates[-1]} → {covered_dates[0]})")
            for d, items in sorted(day_groups.items(), reverse=True):
                cap_note = "(capped)" if len(items) >= max_per_day else ""
                print(f"    {d}: {len(items)} items {cap_note}")
        else:
            print(f"  Warning: 0 items within the date window.")

        return result


def _get_bounds(page) -> tuple:
    """
    Return (newest_dt, oldest_dt, newest_raw, oldest_raw) for all news items in DOM.
    Uses robust _parse_date_flexible so None / unparseable dates are surfaced clearly.
    """
    try:
        raw = page.evaluate(
            """() => {
                const items = Array.from(document.querySelectorAll('ul.news-box li.news-item'));
                if (items.length === 0) return { newest_raw: null, oldest_raw: null };
                const getTime = (el) => {
                    const spans = el.querySelectorAll('.news-meta span.ellipsis');
                    for (const s of spans) {
                        if (s.classList.contains('news-time')) return s.textContent.trim();
                    }
                    for (const s of spans) {
                        if (s.classList.contains('news-source')) continue;
                        return s.textContent.trim();
                    }
                    return 'N/A';
                };
                return {
                    newest_raw: getTime(items[0]),
                    oldest_raw: getTime(items[items.length - 1]),
                };
            }"""
        )
        newest_dt = _parse_date_flexible(raw["newest_raw"]) if raw["newest_raw"] else None
        oldest_dt = _parse_date_flexible(raw["oldest_raw"]) if raw["oldest_raw"] else None
        return (newest_dt, oldest_dt, raw["newest_raw"], raw["oldest_raw"])
    except Exception as e:
        return (None, None, None, None)


def _parse_date_flexible(date_str: str) -> datetime | None:
    """
    Robust date parser matching DailySentimentBuilder._parse_date from test.py.
    Handles relative strings like '3 days ago', explicit date formats, and
    falls back to dateparser as a last resort.
    """
    if not date_str or date_str == "N/A":
        return None
    date_str = str(date_str).strip()
    date_lower = date_str.lower()

    # Relative / fuzzy strings
    if any(x in date_lower for x in ["hour", "minute", "just now", "ago"]):
        return datetime.now()
    if "day" in date_lower:
        m = re.search(r"(\d+)", date_str)
        if m:
            try:
                return datetime.now() - timedelta(days=int(m.group(1)))
            except Exception:
                pass
    if "week" in date_lower:
        m = re.search(r"(\d+)", date_str)
        if m:
            try:
                return datetime.now() - timedelta(weeks=int(m.group(1)))
            except Exception:
                pass
    if "month" in date_lower:
        m = re.search(r"(\d+)", date_str)
        if m:
            try:
                return datetime.now() - timedelta(days=int(m.group(1)) * 30)
            except Exception:
                pass

    # Explicit formats
    formats = [
        "%Y-%m-%d", "%Y/%m/%d",
        "%d/%m/%Y", "%m/%d/%Y",
        "%B %d, %Y", "%b %d, %Y",
        "%d %B %Y", "%d %b %Y",
        "%B %d", "%b %d",
        "%d %B", "%d %b",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.year == 1900:
                dt = dt.replace(year=datetime.now().year)
            return dt
        except Exception:
            continue

    # Fallback: dateparser
    try:
        return dateparser.parse(date_str, settings={"PREFER_DATES_FROM": "past"})
    except Exception:
        pass
    return None

if __name__ == "__main__":
    print("=" * 60)
    print("Test A: Xiaomi (01810-HK), last 10 days, max 2/day")
    print("=" * 60)
    result = scrape_futunn_recent_days_news(
        "01810-HK", num_days=10, max_per_day=2, headless=True
    )
    print(f"\nTotal items returned: {len(result)}")
    for item in result:
        print(f"  [{item.get('parsed_date_str', 'N/A')}] {item['title'][:60]}")

    print("\n" + "=" * 60)
    print("Test B: TSLA-US, last 20 days, max 3/day")
    print("=" * 60)
    result2 = scrape_futunn_recent_days_news(
        "TSLA-US", num_days=20, max_per_day=3, headless=True
    )
    print(f"\nTotal items returned: {len(result2)}")
    for item in result2:
        print(f"  [{item.get('parsed_date_str', 'N/A')}] {item['title'][:60]}")
