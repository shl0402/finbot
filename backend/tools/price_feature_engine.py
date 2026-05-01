import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def format_ticker(ticker: str) -> str:
    ticker = str(ticker).strip().upper()
    if ticker.endswith("-HK"):
        # Convert Futunn format (00027-HK) to Yahoo Finance format (0027.HK)
        numeric = ticker[:-3].lstrip("0")
        return f"{numeric.zfill(4)}.HK" if numeric else "0000.HK"
    if ticker.endswith("-US"):
        # Convert format like TSLA-US to TSLA
        return ticker[:-3]
    # If the ticker is just digits, assume it's a HK stock
    if ticker.isdigit():
        return f"{ticker.zfill(4)}.HK"
    return ticker

def compute_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['returns'] = df['close'].pct_change()
    df['volatility_10d'] = df['returns'].rolling(10).std()
    df['volume_change'] = df['volume'].pct_change().fillna(0)
    df['price_range'] = (df['high'] - df['low']) / df['close']
    
    # RSI (14 days)
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # MACD (12,26,9)
    ema_fast = df['close'].ewm(span=12).mean()
    ema_slow = df['close'].ewm(span=26).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=9).mean()
    df['MACD'] = macd - signal_line
    
    # VWAP (20 days)
    df['vwap'] = (df['close'] * df['volume']).rolling(20).sum() / df['volume'].rolling(20).sum()
    
    # HSI volatility proxy (using own volatility as placeholder)
    df['hsi_volatility'] = df['volatility_10d'].rolling(20).mean().shift(1).fillna(df['volatility_10d'].mean())
    return df

def get_price_features(ticker: str, lookback: int = 20, fetch_days: int = 100) -> pd.DataFrame:
    formatted_ticker = format_ticker(ticker)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=fetch_days)
    data = yf.download(formatted_ticker, start=start_date, end=end_date, progress=False)
    if data.empty:
        raise ValueError(f"No price data for ticker {ticker} ({formatted_ticker})")

    df = data.reset_index()
    # Properly flatten MultiIndex columns: take the first level (Price, Volume, etc.)
    # and discard the ticker level (TSLA, AAPL, etc.)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.rename(columns={
        'Date': 'date', 'Open': 'open', 'High': 'high',
        'Low': 'low', 'Close': 'close', 'Volume': 'volume'
    }, inplace=True)
    df['date'] = pd.to_datetime(df['date']).dt.date

    df = compute_technical_features(df)
    # Drop rows with any NaN (from rolling calculations)
    df = df.dropna().reset_index(drop=True)
    
    if len(df) < lookback:
        raise ValueError(f"After feature engineering, only {len(df)} rows available, need {lookback}. "
                         f"Try increasing fetch_days or check data quality for {ticker}")
    
    # Return last `lookback` rows
    price_cols = ['close', 'Volume', 'returns', 'volatility_10d', 'volume_change',
                  'price_range', 'RSI', 'MACD', 'vwap', 'hsi_volatility']
    df.rename(columns={'volume': 'Volume'}, inplace=True)
    result = df[price_cols].iloc[-lookback:].reset_index(drop=True)
    return result

if __name__ == "__main__":
    # for test_ticker in ["tsla", "700", "0700.HK", "NVDA"]:
    for test_ticker in ["27", "0027.HK", "00027-HK", "00027.HK", "00027"]:
        print(f"\n--- Testing for {test_ticker} ---")
        try:
            features_df = get_price_features(test_ticker)
            print(features_df.head(5))
        except Exception as e:
            print(f"Error fetching for {test_ticker}: {e}")