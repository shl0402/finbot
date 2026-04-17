import yfinance as yf
import pandas as pd
from datetime import datetime
from typing import Dict, Optional, List

def get_ohlc(ticker: str) -> Optional[Dict]:
    """
    Get real-time OHLC data for a given ticker using yfinance.

    :param ticker: Stock ticker (e.g., 'AAPL', '0005.HK', 'TSLA')
    :return: Dictionary with OHLC data
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")

        if hist.empty:
            print(f"No data for {ticker}")
            return None

        info = stock.info

        return {
            'ticker': ticker,
            'timestamp': datetime.now().isoformat(),
            'open': round(hist['Open'].iloc[-1], 2),
            'high': round(hist['High'].iloc[-1], 2),
            'low': round(hist['Low'].iloc[-1], 2),
            'close': round(hist['Close'].iloc[-1], 2),
            'current_price': round(info.get('regularMarketPrice', hist['Close'].iloc[-1]), 2),
            'volume': int(hist['Volume'].iloc[-1]),
            'previous_close': round(info.get('previousClose', 0), 2),
            'day_range': f"{round(hist['Low'].iloc[-1], 2)} - {round(hist['High'].iloc[-1], 2)}",
            'week52_range': f"{info.get('fiftyTwoWeekLow', 'N/A')} - {info.get('fiftyTwoWeekHigh', 'N/A')}"
        }

    except Exception as e:
        print(f"Error: {e}")
        return None


def get_multiple_ohlc(tickers: List[str]) -> pd.DataFrame:
    """
    Get OHLC data for multiple tickers and return as DataFrame.
    """
    data = []
    for ticker in tickers:
        ohlc = get_ohlc(ticker)
        if ohlc:
            data.append(ohlc)

    return pd.DataFrame(data)


# Quick test
if __name__ == "__main__":
    # Single ticker
    aapl = get_ohlc("AAPL")
    print(aapl)

    # Multiple tickers
    tickers = ["AAPL", "TSLA", "0700.HK", "0005.HK"]
    df = get_multiple_ohlc(tickers)
    print("\n", df.to_string(index=False))

    # Save to CSV
    df.to_csv("ohlc_data.csv", index=False)