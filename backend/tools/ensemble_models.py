"""
Local model loader for the ensemble prediction pipeline.
Loads GBM, LSTM, and meta-stacking model from tools/models/.
"""

from __future__ import annotations

import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import tensorflow as tf

_TOOLS_DIR = Path(__file__).parent
_MODEL_DIR = _TOOLS_DIR / "models"


class ModelLoader:
    """
    Load and run the GBM + LSTM + meta-stacking ensemble model.
    All paths are relative to this file's location (tools/models/).
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def _load(self):
        if self._loaded:
            return

        self.gbm = joblib.load(_MODEL_DIR / "gbm_model.pkl")
        self.lstm = tf.keras.models.load_model(str(_MODEL_DIR / "lstm_model.keras"))
        self.meta = joblib.load(_MODEL_DIR / "meta_model.pkl")
        self.price_scaler = joblib.load(_MODEL_DIR / "global_price_scaler.pkl")
        self.sent_scaler = joblib.load(_MODEL_DIR / "global_sent_scaler.pkl")
        meta_info = joblib.load(_MODEL_DIR / "metadata.pkl")
        self.lookback = meta_info["lookback"]
        self.threshold = meta_info["threshold"]
        self._loaded = True
        print(f"[ModelLoader] Loaded. lookback={self.lookback}, threshold={self.threshold}")

    def predict_from_features(self, price_df: pd.DataFrame, sent_df: pd.DataFrame) -> tuple[float, str]:
        """
        Run ensemble prediction.

        Args:
            price_df: DataFrame with 20 rows x 10 price features.
                      Columns: close, Volume, returns, volatility_10d, volume_change,
                               price_range, RSI, MACD, vwap, hsi_volatility
            sent_df: DataFrame with 20 rows x 8 sentiment features.
                     Columns: sentiment_mean, sentiment_lag_1, sentiment_lag_2,
                              sentiment_lag_3, news_count, news_lag_1, news_lag_2,
                              news_lag_3

        Returns:
            (probability_up, signal) where signal is "BUY" or "SELL".
        """
        self._load()

        # Per-column NaN report before scaling
        price_vals = price_df.values
        sent_vals = sent_df.values
        print(f"       [DEBUG] price_df NaN per col:  {dict(zip(price_df.columns, np.isnan(price_vals).sum(axis=0)))}")
        print(f"       [DEBUG] sent_df NaN per col:   {dict(zip(sent_df.columns, np.isnan(sent_vals).sum(axis=0)))}")

        # Fill NaN in sent_df (lag columns) with 0 before scaling.
        # The scaler was fit on training data that had these NaN lag values;
        # StandardScaler then propagates NaN during transform. Using 0 matches
        # the padding rows and is semantically correct (no prior data = neutral).
        if np.isnan(sent_vals).any():
            print(f"       [WARNING] sent_df contains {np.isnan(sent_vals).sum()} NaN values — filling with 0")
            sent_vals = np.nan_to_num(sent_vals, nan=0.0)

        price_scaled = self.price_scaler.transform(price_vals)
        sent_scaled = self.sent_scaler.transform(sent_vals)

        # Report NaN in scaled arrays
        print(f"       [DEBUG] price_scaled shape={price_scaled.shape}, NaN={np.isnan(price_scaled).sum()}")
        print(f"       [DEBUG] sent_scaled  shape={sent_scaled.shape}, NaN={np.isnan(sent_scaled).sum()}")

        # LSTM path: 3D tensor (batch=1, lookback=20, features)
        price_seq = price_scaled.reshape(1, self.lookback, -1)
        sent_seq = sent_scaled.reshape(1, self.lookback, -1)
        prob_lstm_raw = self.lstm.predict([price_seq, sent_seq], verbose=0)[0][0]
        prob_lstm = float(prob_lstm_raw)
        if np.isnan(prob_lstm):
            print(f"       [WARNING] LSTM output is NaN ({prob_lstm_raw}) — defaulting to 0.5")
            prob_lstm = 0.5

        # GBM path: flattened features with statistical aggregations
        flat = np.concatenate([
            price_scaled.mean(axis=0),    # 10 features
            price_scaled.max(axis=0),    # 10 features
            price_scaled.std(axis=0),    # 10 features
            sent_scaled.mean(axis=0),    # 8 features
            sent_scaled.max(axis=0),    # 8 features
            sent_scaled.std(axis=0),     # 8 features
            price_scaled[-1],            # 10 features (last row)
            sent_scaled[-1],             # 8 features (last row)
        ]).reshape(1, -1)
        if np.isnan(flat).any():
            print(f"       [WARNING] GBM input contains {np.isnan(flat).sum()} NaN values — filling with 0")
            flat = np.nan_to_num(flat, nan=0.0)
        prob_gbm = float(self.gbm.predict_proba(flat)[0][1])

        # Stacking meta model
        meta_input = np.array([[prob_lstm, prob_gbm]])
        if np.isnan(meta_input).any():
            print(f"       [WARNING] Meta input contains NaN — using GBM probability only")
            return prob_gbm, ("BUY" if prob_gbm > self.threshold else "SELL")
        prob = float(self.meta.predict_proba(meta_input)[0][1])
        signal = "BUY" if prob > self.threshold else "SELL"
        return prob, signal
