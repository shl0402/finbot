from playwright.sync_api import sync_playwright
import json

def scrape_futunn_sectors(headless: bool = True) -> list:
    """
    Scrapes the Futunn HK industry heatmap.
    
    :param headless: If True, runs the browser invisibly. If False, opens a visible browser window.
    """
    base_url = "https://www.futunn.com"
    target_url = f"{base_url}/en/heatmap-hk/industry"
    
    with sync_playwright() as p:
        # Launch browser with the requested headless mode and stealth arguments
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
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Mask the webdriver property to help bypass bot detection
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = context.new_page()
        
        mode_text = "headless (invisible)" if headless else "headed (visible)"
        print(f"Loading {target_url} in {mode_text} mode...")
        page.goto(target_url)
        
        # Wait until the SVG cells are injected into the DOM
        try:
            page.wait_for_function(
                "() => document.querySelectorAll('svg.treemap-svg a.cell').length > 0", 
                timeout=20000
            )
        except Exception as e:
            print("Timeout waiting for SVG cells to load. The site might be loading slowly or blocking the request.")
            browser.close()
            return []
        
        # Extract data using browser-side JavaScript to avoid Playwright SVG limitations
        extracted_data = page.evaluate('''() => {
            const cells = document.querySelectorAll('svg.treemap-svg a.cell');
            const data = [];
            
            cells.forEach(cell => {
                // Grab the link from xlink:href
                let href = cell.getAttribute('xlink:href') || cell.getAttribute('href');
                
                // Find all tspans inside this cell
                const tspans = cell.querySelectorAll('text tspan');
                
                if (tspans.length >= 2) {
                    const sectorName = tspans[0].textContent.trim();
                    const percentChange = tspans[1].textContent.trim();
                    
                    if (sectorName && percentChange) {
                        data.push({
                            sector: sectorName,
                            change_percent: percentChange,
                            link: href ? href : "N/A"
                        });
                    }
                }
            });
            return data;
        }''')
        
        browser.close()
        
        # Append the base URL to the extracted relative links
        for item in extracted_data:
            if item['link'] != "N/A":
                item['link'] = f"{base_url}{item['link']}"
                
        # Convert strings like "+0.61%" or "-3.25%" into floats for sorting
        def parse_percent(val_str: str) -> float:
            try:
                return float(val_str.replace('%', '').replace('+', '').strip())
            except ValueError:
                return -9999.0 

        # Sort the data: highest positive percentage to lowest negative percentage
        extracted_data.sort(key=lambda x: parse_percent(x['change_percent']), reverse=True)
        
        return extracted_data

if __name__ == "__main__":
    # Call with headless=False to watch the browser in action, or leave empty/True to run silently
    result = scrape_futunn_sectors(headless=True)
    print(json.dumps(result, indent=4, ensure_ascii=False))