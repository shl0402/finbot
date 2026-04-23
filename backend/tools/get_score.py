import json

# Import the scraper function from your local file
# Ensure tradingview_stock_analysis_scrawler.py is in the same directory
try:
    from tradingview_stock_analysis_scrawler import scrape_tradingview_stock_analysis
except ImportError:
    print("Warning: tradingview_stock_analysis_scrawler.py not found. Tool will fail without it.")

def parse_financial_value(val_str):
    """Converts TradingView formatted strings into standard floats."""
    if not isinstance(val_str, str):
        return val_str
    
    val_str = val_str.replace(',', '').strip()
    val_str = val_str.replace('−', '-') 
    
    if val_str == '—' or val_str == 'N/A' or val_str == '':
        return None
        
    multiplier = 1.0
    if val_str.endswith('B'):
        multiplier = 1e9
        val_str = val_str[:-1]
    elif val_str.endswith('T'):
        multiplier = 1e12
        val_str = val_str[:-1]
    elif val_str.endswith('M'):
        multiplier = 1e6
        val_str = val_str[:-1]
        
    try:
        return float(val_str) * multiplier
    except ValueError:
        return None

def extract_metric(data, periodicity, metric_name):
    """Finds a specific metric in the JSON and returns its parsed values."""
    for item in data.get("statistics", {}).get(periodicity, []):
        if item.get("metric") == metric_name:
            raw_values = item.get("values", {})
            return {k: parse_financial_value(v) for k, v in raw_values.items()}
    return {}

def get_current_and_historical(values_dict):
    """Extracts the 'Current' value and calculates the historical average."""
    if not values_dict:
        return None, None
        
    current = values_dict.get('Current')
    historical_data = [v for k, v in values_dict.items() if k != 'Current' and v is not None]
    historical_avg = sum(historical_data) / len(historical_data) if historical_data else None
    
    return current, historical_avg

def calculate_scores(json_data):
    """Main scoring engine."""
    
    # Extraction
    pe_vals = extract_metric(json_data, "annual", "Price to earnings ratio")
    shares_vals = extract_metric(json_data, "annual", "Total common shares outstanding")
    net_margin_vals = extract_metric(json_data, "quarterly", "Net margin %")
    roe_vals = extract_metric(json_data, "quarterly", "Return on equity %")
    current_ratio_vals = extract_metric(json_data, "quarterly", "Current ratio")
    debt_equity_vals = extract_metric(json_data, "quarterly", "Debt to equity ratio")

    pe_curr, pe_hist = get_current_and_historical(pe_vals)
    net_margin_curr, net_margin_hist = get_current_and_historical(net_margin_vals)
    roe_curr, roe_hist = get_current_and_historical(roe_vals)
    cr_curr, cr_hist = get_current_and_historical(current_ratio_vals)
    de_curr, de_hist = get_current_and_historical(debt_equity_vals)
    
    shares_curr = shares_vals.get("Current") if shares_vals else None
    historical_shares = [v for k, v in (shares_vals or {}).items() if k != 'Current' and v is not None]
    shares_prev = historical_shares[-1] if historical_shares else None

    # --- S_dir Calculation ---
    val_score = 0.5
    if pe_curr and pe_hist:
        val_score = max(0.0, min(1.0, 0.5 * (pe_hist / pe_curr))) 
        
    share_score = 0.5
    if shares_curr and shares_prev:
        if shares_curr < shares_prev: share_score = 1.0     
        elif shares_curr > shares_prev: share_score = 0.0    
        
    engine_a = (val_score * 0.7) + (share_score * 0.3)
    
    margin_score = 0.5
    if net_margin_curr and net_margin_hist:
        margin_score = 0.9 if net_margin_curr > net_margin_hist else 0.2
        
    roe_score = 0.5
    if roe_curr:
        if roe_curr > 15.0: roe_score = 0.8
        elif roe_curr < 5.0: roe_score = 0.1
        
    engine_b = (margin_score * 0.6) + (roe_score * 0.4)
    
    health_score = 0.5
    if cr_curr:
        if cr_curr > 1.2: health_score = 0.7
        elif cr_curr < 1.0: health_score = 0.2
        
    debt_score = 0.5
    if de_curr and de_hist:
        if de_curr < de_hist: debt_score = 0.8
        elif de_curr > (de_hist * 1.1): debt_score = 0.2 
        
    engine_c = (health_score * 0.5) + (debt_score * 0.5)
    
    s_dir = (engine_a * 0.4) + (engine_b * 0.4) + (engine_c * 0.2)
    
    # --- S_disp Calculation ---
    disp_roc = 0.1
    disp_extreme = 0.1
    
    historical_margins = [v for k, v in (net_margin_vals or {}).items() if k != 'Current' and v is not None]
    if net_margin_curr and len(historical_margins) >= 1:
        prev_margin = historical_margins[-1]
        if prev_margin != 0:
            rel_change = abs((net_margin_curr - prev_margin) / prev_margin)
            if rel_change > 0.20: 
                disp_roc = 0.9
                
    if pe_curr:
        if pe_curr > 80 or pe_curr < 5:
            disp_extreme = max(disp_extreme, 0.9)
    if cr_curr:
        if cr_curr < 0.8:
            disp_extreme = 1.0 
            
    s_disp = (disp_roc * 0.6) + (disp_extreme * 0.4)

    return {
        "symbol": json_data.get("symbol", "Unknown"),
        "company_name": json_data.get("company_name", "Unknown"),
        "S_dir": round(s_dir, 3),
        "S_disp": round(s_disp, 3)
    }

def analyze_stock_fundamentals(exchange: str, symbol: str) -> dict:
    """
    Tool function designed for LLM usage.
    Scrapes TradingView and returns fundamental quantitative scores.
    """
    try:
        # Trigger the external web scraper
        raw_data = scrape_tradingview_stock_analysis(exchange, symbol, headless=True)
        
        # Ensure it's parsed into a dict if the scraper returns a JSON string
        if isinstance(raw_data, str):
            data = json.loads(raw_data)
        else:
            data = raw_data
            
        # Calculate and return the scores
        result = calculate_scores(data)
        result["status"] = "success"
        return result
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "exchange": exchange,
            "symbol": symbol
        }

if __name__ == "__main__":
    # Test block for main execution
    print("Running scraper for SZSE:002594 (BYD)...")
    
    # The LLM will call analyze_stock_fundamentals internally
    test_result = analyze_stock_fundamentals("SZSE", "002594")
    
    if test_result.get("status") == "success":
        print(f"\nResults for {test_result['company_name']} ({test_result['symbol']})")
        print("-" * 40)
        print(f"Directional Score (S_dir):  {test_result['S_dir']}")
        print(f"Displacement Score (S_disp): {test_result['S_disp']}")
    else:
        print(f"Error fetching data: {test_result.get('message')}")