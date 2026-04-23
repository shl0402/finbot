import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Union

def get_history(ticker: str, days: int = 10) -> Optional[Dict]:
    """
    Get historical OHLCV data for X days (default 10).
    :param ticker: Stock ticker (e.g., 'AAPL', '0005.HK')
    :param days: Number of days of history (default 10)
    :return: Dict with dates and OHLCV arrays
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=f"{days}d")

        if hist.empty:
            print(f"No data for {ticker}")
            return None

        return {
            'ticker': ticker,
            'days': days,
            'dates': hist.index.strftime('%Y-%m-%d').tolist(),
            'open': hist['Open'].round(2).tolist(),
            'high': hist['High'].round(2).tolist(),
            'low': hist['Low'].round(2).tolist(),
            'close': hist['Close'].round(2).tolist(),
            'volume': hist['Volume'].astype(int).tolist(),
            'latest_price': round(hist['Close'].iloc[-1], 2),
            'latest_volume': int(hist['Volume'].iloc[-1]),
        }
    except Exception as e:
        return {'error': str(e), 'ticker': ticker}


def get_multiple_history(tickers: List[str], days: int = 10) -> List[Dict]:
    """Get historical data for multiple tickers."""
    return [get_history(t, days) for t in tickers if get_history(t, days)]
