from playwright.sync_api import sync_playwright
import json

def scrape_tradingview_sectors(headless: bool = True) -> list:
    """
    Scrapes the TradingView Hong Kong sectors list, including both Overview and Performance data.
    
    :param headless: If True, runs the browser invisibly. If False, opens a visible browser window.
    """
    base_url = "https://www.tradingview.com"
    target_url = f"{base_url}/markets/stocks-hong-kong/sectorandindustry-sector/"
    
    with sync_playwright() as p:
        # Launch browser with stealth arguments
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
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Mask the webdriver property
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = context.new_page()
        mode_text = "headless (invisible)" if headless else "headed (visible)"
        print(f"Loading {target_url} in {mode_text} mode...")
        page.goto(target_url, wait_until="domcontentloaded")
        
        # 1. Wait for the initial "Overview" table to load
        try:
            page.wait_for_selector('tbody[data-testid="selectable-rows-table-body"] tr', timeout=15000)
        except Exception:
            print("Timeout waiting for TradingView table to load.")
            browser.close()
            return []
        
        # 2. Scrape Overview Data
        print("Extracting Overview data...")
        overview_data = page.evaluate('''() => {
            const rows = document.querySelectorAll('tbody[data-testid="selectable-rows-table-body"] tr');
            const data = {};
            
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if(cells.length >= 7) {
                    const linkEl = cells[0].querySelector('a');
                    const sectorName = linkEl ? linkEl.textContent.trim() : cells[0].textContent.trim();
                    const href = linkEl ? linkEl.getAttribute('href') : "N/A";
                    
                    // Store in an object mapped by sectorName for easy merging later
                    data[sectorName] = {
                        sector: sectorName,
                        link: href,
                        market_cap: cells[1].textContent.trim(),
                        dividend_yield: cells[2].textContent.trim(),
                        change_percent: cells[3].textContent.trim(),
                        volume: cells[4].textContent.trim(),
                        industries_count: cells[5].textContent.trim(),
                        stocks_count: cells[6].textContent.trim()
                    };
                }
            });
            return data;
        }''')
        
        # 3. Click the "Performance" tab
        print("Switching to Performance tab...")
        page.click('button#performance')
        
        # Wait for the table to update with the new Performance columns (e.g., 1W, 1M, 3M)
        try:
            page.wait_for_selector('th[data-field="Performance|Interval1W"]', timeout=10000)
        except Exception:
            print("Timeout waiting for Performance tab to render.")
            browser.close()
            return []
            
        # 4. Scrape Performance Data
        print("Extracting Performance data...")
        performance_data = page.evaluate('''() => {
            const rows = document.querySelectorAll('tbody[data-testid="selectable-rows-table-body"] tr');
            const data = {};
            
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                // Performance table contains 11 columns
                if(cells.length >= 11) {
                    const linkEl = cells[0].querySelector('a');
                    const sectorName = linkEl ? linkEl.textContent.trim() : cells[0].textContent.trim();
                    
                    data[sectorName] = {
                        perf_1w: cells[2].textContent.trim(),
                        perf_1m: cells[3].textContent.trim(),
                        perf_3m: cells[4].textContent.trim(),
                        perf_6m: cells[5].textContent.trim(),
                        perf_ytd: cells[6].textContent.trim(),
                        perf_1y: cells[7].textContent.trim(),
                        perf_5y: cells[8].textContent.trim(),
                        perf_10y: cells[9].textContent.trim(),
                        perf_all_time: cells[10].textContent.trim()
                    };
                }
            });
            return data;
        }''')
        
        browser.close()
        
        # 5. Merge the two datasets and format output
        final_data = []
        for sector, overview in overview_data.items():
            # Grab matching performance data, default to empty dict if missing
            perf = performance_data.get(sector, {})
            
            # Merge both dictionaries
            merged = {**overview, **perf}
            
            # Fix relative links
            if merged['link'] != "N/A":
                merged['link'] = f"{base_url}{merged['link']}"
                
            final_data.append(merged)
                
        # Helper to convert strings into floats for sorting
        def parse_percent(val_str: str) -> float:
            try:
                # Handle TradingView's unicode minus sign '\u2212'
                clean_str = val_str.replace('%', '').replace('+', '').replace('−', '-').strip()
                return float(clean_str)
            except ValueError:
                return -9999.0 

        # Sort the data: highest positive percentage to lowest negative percentage
        final_data.sort(key=lambda x: parse_percent(x['change_percent']), reverse=True)
        
        return final_data

if __name__ == "__main__":
    result = scrape_tradingview_sectors(headless=True)
    print(json.dumps(result, indent=4, ensure_ascii=False))