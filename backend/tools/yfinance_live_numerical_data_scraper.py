import yfinance as yf
import pandas as pd
from datetime import datetime
from typing import Dict, Optional, List, Any


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
        }

    except Exception as e:
        return {'error': str(e), 'ticker': ticker}


def get_multiple_ohlc(tickers: List[str]) -> list[Any]:
    """
    Get OHLC data for multiple tickers and return as DataFrame.
    """
    data = []
    for ticker in tickers:
        ohlc = get_ohlc(ticker)
        if ohlc:
            data.append(ohlc)

    return data