import os
import re
import sys
import time
from typing import Optional, Dict, Any, List, Tuple
from functools import lru_cache

tools_dir = os.path.dirname(os.path.abspath(__file__))
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

# Tools imports
from futunn_company_info_scrawler import scrape_futunn_stock_info
from futunn_recent_news_link_scrawler import scrape_futunn_stock_news
from tradingview_stock_info_scrawler import scrape_tradingview_stock
from tradingview_stock_analysis_scrawler import scrape_tradingview_stock_analysis
from futunn_sector_change_scrawler import scrape_futunn_sectors
from tradingview_sector_change_scrawler import scrape_tradingview_sectors
from yfinance_sector_change_scrawler import scrape_yfinance_sectors

# ── Mapping Cache ──────────────────────────────────────────────────────────────

_MAPPING_CACHE: Dict[str, List[Tuple[List[str], str]]] = {}


def _load_mapping_file(filename: str) -> List[Tuple[List[str], str]]:
    """Load a mapping file into [(aliases, mapped_value), ...]. Cached per file."""
    if filename in _MAPPING_CACHE:
        return _MAPPING_CACHE[filename]

    tools_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(tools_dir, filename)
    entries: List[Tuple[List[str], str]] = []

    if not os.path.exists(path):
        print(f"Mapping file not found: {path}")
        return entries

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "]:" in line:
                    aliases_part, mapped_value = line.split("]:", 1)
                    aliases_part = aliases_part.strip()[1:]
                    aliases = [a.strip().lower() for a in aliases_part.split(",")]
                    mapped_value = mapped_value.strip()
                    entries.append((aliases, mapped_value))
        _MAPPING_CACHE[filename] = entries
        print(f"Loaded {len(entries)} entries from {filename}")
    except Exception as e:
        print(f"Error reading {filename}: {e}")

    return entries


@lru_cache(maxsize=None)
def _get_all_aliases(filename: str) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """
    Return all aliases and their corresponding mapped values as flat tuples.
    Cached so we only load each mapping file once.
    """
    entries = _load_mapping_file(filename)
    all_aliases: List[str] = []
    all_values: List[str] = []
    for aliases, mapped in entries:
        all_aliases.extend(aliases)
        all_values.extend([mapped] * len(aliases))
    return tuple(all_aliases), tuple(all_values)


def _fuzzy_match(query: str, filename: str, threshold: int = 72) -> Optional[str]:
    """
    Find the best fuzzy match for `query` in `filename`'s mapping.
    Returns the mapped value if the best match scores >= threshold, else None.
    """
    from rapidfuzz import process

    all_aliases, all_values = _get_all_aliases(filename)
    if not all_aliases:
        return None

    query_lower = query.lower().strip()

    # Exact match first (fast path)
    for i, alias in enumerate(all_aliases):
        if alias == query_lower:
            return all_values[i]

    # Fuzzy match — find best candidate
    best = process.extractOne(query_lower, all_aliases)  # default WRatio handles typos well
    if best is None:
        return None

    matched_alias, score, index = best
    if score < threshold:
        return None

    return all_values[index]


def extract_futunn_stock_code(param: str) -> Optional[str]:
    """Passes the mapped stock code cleanly like '01211-HK' for Futunn."""
    # Since we are feeding it directly from mapping, it just needs to exist
    return param

def extract_tradingview_params(param: str) -> Optional[Dict[str, str]]:
    """Extracts exchange and ticker from mapped parameter (e.g. 'NASDAQ-TSLA')."""
    match = re.search(r'([A-Za-z0-9]+)-([A-Za-z0-9.]+)', param)
    if match:
        return {"exchange": match.group(1), "ticker": match.group(2)}
    return None

def get_mapped_entity(stock_name: str, platform_domain: str) -> str:
    """
    Looks up `stock_name` in the mapping file for `platform_domain`.
    First tries exact match, then falls back to fuzzy matching.

    Returns the mapped symbol (e.g. '01024-HK') or the original name if no match found.
    """
    platform_lower = platform_domain.split(".")[0].lower()
    if platform_lower == "tradingview":
        mapping_file = "tradingview_mapping.txt"
    elif platform_lower == "futunn":
        mapping_file = "futunn_entity_mapping.txt"
    else:
        return stock_name

    # Fuzzy match (handles typos like "kun lun" → "kunlun-energy")
    fuzzy_result = _fuzzy_match(stock_name, mapping_file)
    if fuzzy_result is not None:
        print(f"Fuzzy matched '{stock_name}' → '{fuzzy_result}'")
        return fuzzy_result

    # No match at all — return as-is
    print(f"No mapping found for '{stock_name}' — using raw name")
    return stock_name

def run_scraper_manager(stock_name: str, mode: str, max_retries: int = 1) -> Any:
    """
    Manager to try different URLs up to 10 times until success.
    
    Available modes:
    - futunn_info
    - futunn_news
    - tradingview_info
    - tradingview_analysis
    - futunn_sectors
    - tradingview_sectors
    - yfinance_sectors
    """
    
    # Sector modes don't need a stock_name or search, just return directly
    if mode == "futunn_sectors":
        return scrape_futunn_sectors()
    elif mode == "tradingview_sectors":
        return scrape_tradingview_sectors()
    elif mode == "yfinance_sectors":
        return scrape_yfinance_sectors()

    # Settings per mode
    mode_config = {
        "futunn_info": {
            "suffix": "company profile english",
            "domain": "futunn.com",
            "extractor": extract_futunn_stock_code,
            "scraper": scrape_futunn_stock_info
        },
        "futunn_news": {
            "suffix": "recent news english",
            "domain": "futunn.com",
            "extractor": extract_futunn_stock_code,
            "scraper": scrape_futunn_stock_news
        },
        "tradingview_info": {
            "suffix": "stock price",
            "domain": "tradingview.com",
            "extractor": extract_tradingview_params,
            "scraper": scrape_tradingview_stock
        },
        "tradingview_analysis": {
            "suffix": "financials statistics",
            "domain": "tradingview.com",
            "extractor": extract_tradingview_params,
            "scraper": scrape_tradingview_stock_analysis
        }
    }
    
    if mode not in mode_config:
        print(f"Unknown mode: {mode}")
        return None
        
    config = mode_config[mode]
    mapped_stock = get_mapped_entity(stock_name, config['domain'])
    print(f"Using mapped entity: '{mapped_stock}' (Original: '{stock_name}')")
    
    extracted_params = config['extractor'](mapped_stock)
    if not extracted_params:
        print("Failed to extract standardized parameters from the mapped string. Aborting.")
        return None
        
    try:
        if mode in ["futunn_info", "futunn_news"]:
            print(f"Running Futunn scraper with stock_code: {extracted_params}")
            return config['scraper'](stock_code=extracted_params, headless=True)
            
        elif mode in ["tradingview_info", "tradingview_analysis"]:
            print(f"Running TradingView scraper with params: {extracted_params}")
            return config['scraper'](exchange=extracted_params['exchange'], ticker=extracted_params['ticker'])
            
    except Exception as e:
        print(f"Scraper crashed with error: {e}")
        
    return None

if __name__ == "__main__":
    # Test execution
    success_count = 0
    total_tests = 0
    
    stock_modes = ["futunn_info", "futunn_news", "tradingview_info", "tradingview_analysis"]
    sector_modes = ["futunn_sectors", "tradingview_sectors", "yfinance_sectors"]
    entities = ["小米", "tesla"]

    print("Starting integration test for all scrapers...")

    for entity in entities:
        for mode in stock_modes:
            print(f"\n--- Testing mode '{mode}' for '{entity}' ---")
            data = run_scraper_manager(entity, mode)
            if data:
                success_count += 1
            total_tests += 1
            time.sleep(1) # Small delay between requests to be gentle

    for mode in sector_modes:
        print(f"\n--- Testing mode '{mode}' ---")
        data = run_scraper_manager("dummy", mode)
        if data:
            success_count += 1
        total_tests += 1
        time.sleep(1)

    print(f"\nFinal Success rate: {success_count}/{total_tests}")
