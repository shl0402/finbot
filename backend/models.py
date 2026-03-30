# backend/models.py

from pydantic import BaseModel, Field
from typing import Literal

class MetricCard(BaseModel):
    label: str
    value: str
    delta: str | None = None
    delta_color: Literal["normal", "inverse"] | None = None

class RRScore(BaseModel):
    ratio: str  # e.g. "2.8:1"
    description: str  # e.g. "Good — reward outweighs risk"


class MarketDiscoveryPayload(BaseModel):
    type: Literal["metrics"]
    # One stock setup per payload — the frontend stacks them
    symbol: str
    name: str
    metrics: list[MetricCard]
    rr_score: RRScore | None = None  # risk:reward ratio card

class ChartPoint(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float

class ChartPayload(BaseModel):
    type: Literal["chart"]
    symbol: str
    name: str
    chart_data: list[ChartPoint]
    key_stats: list[MetricCard] = []  # e.g. RSI, SMA, Volume
    # ── Sentiment section ──────────────────────────────────────────
    sentiment_score: float | None = None  # -1.0 to 1.0
    sentiment_label: str | None = None  # "Bullish", "Bearish", "Neutral"
    word_cloud: list[dict] = []  # [{"word": str, "score": float, "size": float}]
    top_positive: list[dict] = []  # [{"word": str, "count": int}]
    top_negative: list[dict] = []  # [{"word": str, "count": int}]
    news_count: int | None = None  # total articles/news items analysed

class CodePayload(BaseModel):
    type: Literal["code"]
    language: str
    code: str
    description: str

class ChatRequest(BaseModel):
    history: list[dict]  # [{"role": "user"|"assistant", "content": str, "images"?: [base64_str, ...]}, ...]
    mode: Literal["none", "market_discovery", "stock_deep_analysis"] = "none"

class ChatResponse(BaseModel):
    reply_text: str
    dashboard_payload: MarketDiscoveryPayload | ChartPayload | CodePayload | None
