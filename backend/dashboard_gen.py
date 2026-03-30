# backend/dashboard_gen.py

import random
import numpy as np
from datetime import datetime, timedelta

from models import (
    MarketDiscoveryPayload,
    ChartPayload,
    CodePayload,
    MetricCard,
    ChartPoint,
    RRScore,
)

STOCKS = {
    "TSLA": {"name": "Tesla Inc.", "base": 170.0, "currency": "$"},
    "NVDA": {"name": "NVIDIA Corp.", "base": 880.0, "currency": "$"},
    "AAPL": {"name": "Apple Inc.", "base": 185.0, "currency": "$"},
    "MSFT": {"name": "Microsoft Corp.", "base": 415.0, "currency": "$"},
    "1810.HK": {"name": "Xiaomi Corp.", "base": 16.0, "currency": "HK$"},
    "GOOGL": {"name": "Alphabet Inc.", "base": 175.0, "currency": "$"},
}

METRIC_KEYWORDS = ["market", "discovery", "setup", "picks", "recommend", "best stock", "top"]
CHART_KEYWORDS = ["chart", "analysis", "technical", "nvda", "stock deep", "candlestick", "candle", "price"]
CODE_KEYWORDS = ["code", "python", "script", "run"]

POSITIVE_WORDS = [
    ("beat", 0.9), ("upgrade", 0.85), ("surge", 0.9), ("bullish", 0.95),
    ("record", 0.85), ("growth", 0.80), ("rally", 0.85), ("outperform", 0.80),
    ("breakout", 0.80), ("strong", 0.75), ("profit", 0.80), ("innovate", 0.70),
    ("partnership", 0.75), ("expansion", 0.70), ("buy", 0.85), ("momentum", 0.75),
]
NEGATIVE_WORDS = [
    ("miss", -0.9), ("downgrade", -0.85), ("crash", -0.90), ("bearish", -0.95),
    ("loss", -0.85), ("weak", -0.75), ("risk", -0.70), ("lawsuit", -0.85),
    ("recall", -0.80), ("ban", -0.80), ("decline", -0.80), ("sell", -0.85),
    ("regulation", -0.70), ("layoff", -0.80), ("competition", -0.60), ("overvalued", -0.70),
]
ALL_WORDS = POSITIVE_WORDS + NEGATIVE_WORDS

SENTIMENT_LABEL = {
    (0.60, 1.01): "Bullish",
    (0.20, 0.60): "Slightly Bullish",
    (-0.20, 0.20): "Neutral",
    (-0.60, -0.20): "Slightly Bearish",
    (-1.01, -0.60): "Bearish",
}


def _label_sentiment(score: float) -> str:
    for (low, high), label in SENTIMENT_LABEL.items():
        if low <= score <= high:
            return label
    return "Neutral"


def _make_rr(r: float, stop_pct: float) -> RRScore:
    """Risk:Reward score card."""
    rr = round(r / abs(stop_pct), 1)
    if rr >= 3.0:
        desc = "Excellent — high reward per unit risk"
    elif rr >= 2.0:
        desc = "Good — solid reward-to-risk setup"
    elif rr >= 1.5:
        desc = "Acceptable — minimal edge"
    else:
        desc = "Marginal — limited upside"
    return RRScore(ratio=f"{rr:.1f}:1", description=desc)


def _pick_n(weights: list, n: int) -> list:
    """Sample n items proportionally from a weighted list."""
    total = sum(weights)
    probs = [w / total for w in weights]
    indices = list(range(len(weights)))
    chosen = set()
    while len(chosen) < n:
        pick = random.choices(indices, weights=probs, k=1)[0]
        chosen.add(pick)
    return list(chosen)


def generate(payload_type: str | None) -> MarketDiscoveryPayload | ChartPayload | CodePayload | None:
    if payload_type == "metrics":
        symbol = random.choice(["TSLA", "NVDA", "1810.HK"])
        info = STOCKS[symbol]
        profit = random.choice(["15%", "22%", "37%", "44%", "28%"])
        base = info["base"]
        buy = round(base * random.uniform(0.96, 1.0), 2)
        stop_pct = random.choice([-9, -10, -8])
        stop_val = round(buy * (1 + stop_pct / 100), 2)
        take_val = round(buy * (1 + float(profit.rstrip("%")) / 100), 2)
        currency = info["currency"]
        profit_val = round(take_val - buy, 2)
        risk_val = round(buy - stop_val, 2)

        return MarketDiscoveryPayload(
            type="metrics",
            symbol=symbol,
            name=info["name"],
            metrics=[
                MetricCard(label="Expected Profit", value=profit, delta=f"+{profit}"),
                MetricCard(label="Suggested Buy", value=f"{currency}{buy}"),
                MetricCard(label="Take Profit", value=f"{currency}{take_val}", delta=f"+{profit}"),
                MetricCard(label="Stop Loss", value=f"{currency}{stop_val}", delta=f"{stop_pct}%", delta_color="inverse"),
                MetricCard(label="Profit/Loss Ratio", value=f"{currency}{profit_val}", delta=f"{currency}{risk_val} risk"),
                MetricCard(label="Win Rate Est.", value=random.choice(["55%", "60%", "62%", "58%"])),
            ],
            rr_score=_make_rr(float(profit.rstrip("%")), stop_pct),
        )

    if payload_type == "chart":
        symbol = random.choice(["NVDA", "TSLA", "AAPL", "MSFT", "GOOGL"])
        info = STOCKS.get(symbol, {"name": symbol, "base": 100.0})
        np.random.seed(random.randint(0, 9999))
        n = 30
        dates = [
            (datetime.today() - timedelta(days=n - 1 - i)).strftime("%Y-%m-%d")
            for i in range(n)
        ]
        base_val = info["base"]
        open_vals = (np.random.uniform(base_val * 0.93, base_val * 1.07, n)).tolist()
        close_vals = [o + random.uniform(-5, 5) for o in open_vals]
        high_vals = [max(o, c) + random.uniform(0, 4) for o, c in zip(open_vals, close_vals)]
        low_vals = [min(o, c) - random.uniform(0, 4) for o, c in zip(open_vals, close_vals)]
        chart_data = [
            ChartPoint(
                date=d,
                open=round(o, 2),
                high=round(h, 2),
                low=round(l, 2),
                close=round(c, 2),
            )
            for d, o, h, l, c in zip(dates, open_vals, high_vals, low_vals, close_vals)
        ]

        # ── Key stats (technical indicators) ──────────────────────────
        rsi = round(random.uniform(35, 75), 1)
        sma20 = round(base_val * random.uniform(0.97, 1.03), 2)
        sma50 = round(base_val * random.uniform(0.95, 1.05), 2)
        volume_ratio = round(random.uniform(0.7, 2.5), 1)
        avg_vol = int(random.uniform(30_000_000, 80_000_000))
        macd_hist = round(random.uniform(-3, 3), 2)
        key_stats = [
            MetricCard(label="RSI (14)", value=str(rsi),
                       delta="Overbought" if rsi > 70 else ("Oversold" if rsi < 30 else "Neutral")),
            MetricCard(label="SMA 20", value=f"${sma20}"),
            MetricCard(label="SMA 50", value=f"${sma50}"),
            MetricCard(label="Volume vs Avg", value=f"{volume_ratio}x",
                       delta="High" if volume_ratio > 1.5 else "Normal"),
            MetricCard(label="Avg Volume", value=f"{avg_vol:,.0f}"),
            MetricCard(label="MACD Histogram", value=str(macd_hist),
                       delta_color="normal" if macd_hist > 0 else "inverse"),
        ]

        # ── Sentiment: word cloud + frequency bars ─────────────────────
        news_count = random.randint(25, 120)
        sentiment_score = round(random.uniform(-0.5, 0.8), 2)
        word_weights = [abs(s) for _, s in ALL_WORDS]
        wc_indices = _pick_n(word_weights, 20)
        word_cloud = [
            {
                "word": ALL_WORDS[i][0],
                "score": ALL_WORDS[i][1],
                "size": round(12 + abs(ALL_WORDS[i][1]) * 22 + random.uniform(0, 8), 1),
            }
            for i in wc_indices
        ]
        pos_indices = _pick_n([s for _, s in POSITIVE_WORDS], 6)
        neg_indices = _pick_n([abs(s) for _, s in NEGATIVE_WORDS], 6)
        top_positive = [
            {"word": POSITIVE_WORDS[i][0], "count": random.randint(3, 18)}
            for i in pos_indices
        ]
        top_negative = [
            {"word": NEGATIVE_WORDS[i][0], "count": random.randint(2, 12)}
            for i in neg_indices
        ]

        return ChartPayload(
            type="chart",
            symbol=symbol,
            name=info["name"],
            chart_data=chart_data,
            key_stats=key_stats,
            sentiment_score=sentiment_score,
            sentiment_label=_label_sentiment(sentiment_score),
            word_cloud=word_cloud,
            top_positive=top_positive,
            top_negative=top_negative,
            news_count=news_count,
        )

    if payload_type == "code":
        return CodePayload(
            type="code",
            language="python",
            code='import ollama\n\nresponse = ollama.chat(\n    model="mistral-small3.1:24b-instruct-2503-q4_K_M",\n    messages=[{"role": "user", "content": "Hello!"}],\n)\nprint(response["message"]["content"])',
            description="Query Ollama mistral-small3.1 24B Q4 via the official SDK.",
        )

    return None


def detect_dashboard(prompt: str) -> str | None:
    lower = prompt.lower()
    if any(kw in lower for kw in CHART_KEYWORDS):
        return "chart"
    if any(kw in lower for kw in METRIC_KEYWORDS):
        return "metrics"
    if any(kw in lower for kw in CODE_KEYWORDS):
        return "code"
    return None