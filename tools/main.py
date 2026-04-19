import yaml
import os
import json
import asyncio
import random
import signal
from datetime import datetime
from playwright.async_api import async_playwright
import dateparser

def get_current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def format_futu_urls(stock_code):
    """Returns a list of URLs to try (handles US vs HK fallback)"""
    code_str = str(stock_code).upper()
    
    # If the user already provided the suffix (e.g., AAPL-US or 00700-HK)
    if "-HK" in code_str or "-US" in code_str:
        return [f"https://www.futunn.com/en/stock/{code_str}/news"]
        
    # If it's pure numbers, it's definitively a Hong Kong stock
    if code_str.isdigit():
        return [f"https://www.futunn.com/en/stock/{code_str.zfill(5)}-HK/news"]
        
    # If it's letters without a suffix (like TSLA or AAPL), try US first, then HK
    return [
        f"https://www.futunn.com/en/stock/{code_str}-US/news",
        f"https://www.futunn.com/en/stock/{code_str}-HK/news"
    ]

def load_state(state_file):
    state = {}
    if os.path.exists(state_file):
        with open(state_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    stock_code = data.get("stock_code")
                    if stock_code:
                        state[stock_code] = data
                except json.JSONDecodeError:
                    continue
    return state

async def save_state(stock_code, state_dict, lock, state_file):
    async with lock:
        with open(state_file, 'a', encoding='utf-8') as f:
            record = {"stock_code": stock_code}
            record.update(state_dict)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

async def check_for_captcha(page, stock_code):
    captcha_selectors = [
        "iframe[src*='captcha']",
        "div.geetest_captcha",
        ".captcha-container"
    ]
    for selector in captcha_selectors:
        try:
            if await page.locator(selector).is_visible(timeout=1000):
                print(f"\n[{get_current_time()}] 🚨 CAPTCHA DETECTED FOR [{stock_code}] 🚨")
                print(f"Please switch to the browser window and solve it manually.")
                while await page.locator(selector).is_visible():
                    await asyncio.sleep(3)
                print(f"[{get_current_time()}] ✅ Captcha cleared for [{stock_code}]. Resuming...\n")
                return True
        except Exception:
            pass
    return False

async def process_stock(stock_code, category, config, browser, semaphore, shutdown_event, global_state, state_lock):
    async with semaphore:
        start_limit = datetime.strptime(config['start_date'], "%Y-%m-%d")
        
        # New Smart Stopping Limits
        fallback_limit = datetime.strptime(config.get('fallback_date', '2023-01-01'), "%Y-%m-%d")
        max_articles_limit = config.get('max_articles', 10000)
        state_file = config.get('state_file', 'scraping_progress.jsonl')
        
        end_limit = datetime.strptime(config['end_date'], "%Y-%m-%d")
        selectors = config['sites']['futunn']['selectors']
        
        os.makedirs(f"data/{category}", exist_ok=True)
        filepath = f"data/{category}/{stock_code}.jsonl"
        
        existing_titles = set()
        status_report = {"stock": stock_code, "status": "Success", "new_articles": 0, "error": None}
        oldest_saved_date = None
        
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        existing_titles.add(data['title'])
                    except json.JSONDecodeError:
                        continue
        
        urls_to_try = format_futu_urls(stock_code)
        page = await browser.new_page()
        valid_page_loaded = False
        
        try:
            # === URL FALLBACK ROUTER ===
            for url in urls_to_try:
                print(f"[{get_current_time()}] [{stock_code}] Attempting URL: {url}")
                await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                await check_for_captcha(page, stock_code)
                
                # Verify if the page is a real stock page (wait briefly for news to render)
                await asyncio.sleep(2)
                title = await page.title()
                
                # If page title contains 404, or there are no news containers, try the next URL
                if "404" in title:
                    print(f"[{get_current_time()}] [{stock_code}] 404 detected. Trying fallback URL...")
                    continue
                    
                news_count = await page.locator(selectors['container']).count()
                if news_count > 0:
                    valid_page_loaded = True
                    break 
                else:
                    print(f"[{get_current_time()}] [{stock_code}] No news containers found. Trying fallback URL...")

            if not valid_page_loaded:
                raise Exception("Could not find a valid Futu page (tried US and HK formats).")

            last_height = await page.evaluate("document.body.scrollHeight")
            retries = 0
            max_retries = 10 
            button_selector = "button.add-more-news"
            reached_boundary = False

            js_extract_snippet = """(sel) => {
                let results = [];
                document.querySelectorAll(sel.container).forEach(container => {
                    let titleElem = container.querySelector(sel.title);
                    let dateElem = container.querySelector(sel.date);
                    let sourceElem = container.querySelector(sel.source || 'span.news-source');
                    if (titleElem && dateElem) {
                        results.push({
                            title: titleElem.innerText.trim(),
                            raw_date: dateElem.innerText.trim(),
                            source: sourceElem ? sourceElem.innerText.trim() : "",
                            link: container.getAttribute("href") || ""
                        });
                    }
                });
                return results;
            }"""
            
            while not shutdown_event.is_set() and not reached_boundary:
                popup_close_btn = page.locator("div.gold-flow-content-close")
                if await popup_close_btn.is_visible():
                    try:
                        await popup_close_btn.click(force=True)
                        await asyncio.sleep(random.uniform(1.0, 2.0)) 
                    except: pass

                fail_msg_btn = page.locator("text=/click to try again|loading fail|load failed/i").first
                if await fail_msg_btn.is_visible():
                    try:
                        await fail_msg_btn.click(force=True)
                        await asyncio.sleep(random.uniform(2.0, 3.5))
                    except: pass

                current_batch = await page.evaluate(js_extract_snippet, selectors)
                
                with open(filepath, 'a', encoding='utf-8') as f:
                    for item in current_batch:
                        if item['title'] in existing_titles:
                            continue
                        
                        article_date = dateparser.parse(item['raw_date'], settings={'PREFER_DATES_FROM': 'past'})
                        if not article_date:
                            continue
                            
                        if article_date > end_limit:
                            continue 
                            
                        # === SMART STOPPING LOGIC ===
                        
                        # Stop Condition 1: Hit absolute start date (e.g. 2020)
                        if article_date < start_limit:
                            reached_boundary = True 
                            continue 
                            
                        # Stop Condition 2: Hit max_articles limit AND went deeper than fallback_date
                        total_articles = len(existing_titles) + 1
                        if total_articles >= max_articles_limit and article_date < fallback_limit:
                            print(f"[{get_current_time()}] [{stock_code}] Smart Stop Triggered: {max_articles_limit} articles reached and passed {fallback_limit.strftime('%Y-%m-%d')}.")
                            reached_boundary = True
                            continue
                            
                        if not oldest_saved_date or article_date < oldest_saved_date:
                            oldest_saved_date = article_date

                        record = {
                            "date": article_date.strftime('%Y-%m-%d %H:%M'),
                            "title": item['title'],
                            "source": item['source'],
                            "link": item['link'],
                            "stock_code": stock_code
                        }
                        
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        existing_titles.add(item['title'])
                        status_report["new_articles"] += 1
                        print(f"    -> [SAVED] [{stock_code}] {record['date']} | [{record['source']}] {record['title'][:40]}...")

                if reached_boundary:
                    print(f"[{get_current_time()}] [{stock_code}] Date boundary reached. Stopping load.")
                    break

                load_more_btn = page.locator(button_selector)
                
                if await load_more_btn.is_visible():
                    try:
                        await load_more_btn.click(force=True)
                        await asyncio.sleep(random.uniform(2.0, 3.5)) 
                        await check_for_captcha(page, stock_code)
                        last_height = await page.evaluate("document.body.scrollHeight")
                    except: break
                else:
                    current_items = await page.query_selector_all(selectors['container'])
                    if current_items:
                        try:
                            await current_items[-1].scroll_into_view_if_needed()
                        except: pass
                        await asyncio.sleep(random.uniform(0.5, 1.0))
                        await page.mouse.wheel(0, -1200)
                        await asyncio.sleep(random.uniform(0.5, 1.0))
                        await page.mouse.wheel(0, 2500)
                    else:
                        await page.keyboard.press("End")
                    
                    await asyncio.sleep(random.uniform(2.5, 4.5)) 
                    await check_for_captcha(page, stock_code)
                    
                    new_height = await page.evaluate("document.body.scrollHeight")
                    if new_height == last_height:
                        retries += 1
                        if retries >= max_retries:
                            break
                    else:
                        retries = 0 
                        last_height = new_height

            status_report["status"] = "Interrupted" if shutdown_event.is_set() else "Completed"
            print(f"[{get_current_time()}] [{stock_code}] {status_report['status']}. {status_report['new_articles']} items saved.")
            
        except asyncio.CancelledError:
            print(f"[{get_current_time()}] [⚠️] [{stock_code}] Task cancelled (Manual Override). Forcing save...")
            status_report["status"] = "Interrupted"
        except Exception as e:
            error_msg = str(e).split('\n')[0]
            print(f"[{get_current_time()}] [{stock_code}] ERROR: {error_msg}")
            status_report["status"] = "Failed"
            status_report["error"] = error_msg
        finally:
            try:
                if not page.is_closed():
                    await page.close()
            except Exception:
                pass
            
            stock_state = {
                "status": status_report["status"],
                "oldest_news_scraped": oldest_saved_date.strftime('%Y-%m-%d') if oldest_saved_date else "None",
                "total_articles_saved_this_session": status_report["new_articles"],
                "last_run_time": get_current_time(),
                "error_notes": status_report["error"] if status_report["error"] else "None"
            }
            
            global_state[stock_code] = stock_state
            
            # Pass the dynamically loaded state file to the save function
            await save_state(stock_code, stock_state, state_lock, config.get('state_file', 'scraping_progress.jsonl'))
            
            return status_report

async def main():
    with open("config.yaml", "r", encoding='utf-8') as file:
        config = yaml.safe_load(file)
        
    max_concurrent = config.get('max_concurrent', 5)
    headless_mode = config.get('headless', False) 
    state_file = config.get('state_file', 'scraping_progress.jsonl')
    
    semaphore = asyncio.Semaphore(max_concurrent)
    shutdown_event = asyncio.Event()
    state_lock = asyncio.Lock()
    
    global_state = load_state(state_file)
    summary_results = []

    loop = asyncio.get_running_loop()
    def handle_sigint():
        if not shutdown_event.is_set():
            print("\n" + "="*50)
            print(f"[{get_current_time()}] 🛑 MANUAL OVERRIDE TRIGGERED 🛑")
            print("Sending stop signals to all browsers. Saving current data to files...")
            print("PLEASE WAIT. DO NOT PRESS CTRL+C AGAIN.")
            print("="*50 + "\n")
            shutdown_event.set()
            
    try:
        loop.add_signal_handler(signal.SIGINT, handle_sigint)
    except NotImplementedError:
        pass 
    
    print("==================================================")
    print(f"SCRAPER INITIATED AT: {get_current_time()}")
    print("==================================================")

    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=headless_mode)
        tasks = []
        
        for category, stocks in config['categories'].items():
            for stock_code in stocks:
                if global_state.get(stock_code, {}).get("status") == "Completed":
                    print(f"[{get_current_time()}] [⏭️ SKIP] {stock_code} is already marked as 'Completed' in {state_file}.")
                    continue
                    
                tasks.append(process_stock(stock_code, category, config, browser, semaphore, shutdown_event, global_state, state_lock))
        
        if tasks:
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for res in raw_results:
                if isinstance(res, dict):
                    summary_results.append(res)
                else:
                    print(f"[{get_current_time()}] ⚠️ A task failed to return a valid status report: {res}")
        else:
            print("\nNo stocks left to process! Everything in the config is marked as 'Completed'.")
            
        try:
            await browser.close()
        except:
            pass
        
    print("\n==================================================")
    print("SCRAPE EXECUTION SUMMARY")
    print("==================================================")
    print(f"{'STOCK':<15} | {'STATUS':<15} | {'NEW ARTICLES':<15} | {'NOTES'}")
    print("-" * 70)
    
    total_new = 0
    for res in summary_results:
        stock = res['stock']
        status = res['status']
        new_count = res['new_articles']
        error = res['error'] if res['error'] else ""
        
        total_new += new_count
        print(f"{stock:<15} | {status:<15} | {new_count:<15} | {error}")
        
    print("-" * 70)
    print(f"TOTAL NEW ARTICLES SCRAPED: {total_new}")
    print(f"COMPLETED AT: {get_current_time()}")
    print(f"State saved to: {state_file}")
    print("==================================================")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass