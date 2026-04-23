# backend/models.py

from pydantic import BaseModel, Field
from typing import Literal, Optional


# ── Shared ──────────────────────────────────────────────────────────────────────

class MetricCard(BaseModel):
    label: str
    value: str
    delta: Optional[str] = None
    delta_color: Literal["normal", "inverse"] | None = None


class RRScore(BaseModel):
    ratio: str
    description: str


# ── Thinking Steps ─────────────────────────────────────────────────────────────

class ThinkingStep(BaseModel):
    step_number: int
    phase: Literal[
        "intent_routing",
        "tool_selection",
        "tool_execution",
        "response_generation",
    ]
    status: Literal["active", "success", "failed", "skipped"] = "active"
    content: str
    tool_used: Optional[str] = None
    tool_result_preview: Optional[str] = None


# ── Dashboard Payloads ────────────────────────────────────────────────────────

class MarketDiscoveryPayload(BaseModel):
    type: Literal["metrics"]
    symbol: str
    name: str
    metrics: list[MetricCard]
    rr_score: Optional[RRScore] = None


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
    key_stats: list[MetricCard] = []
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    word_cloud: list[dict] = []
    top_positive: list[dict] = []
    top_negative: list[dict] = []
    news_count: Optional[int] = None


class CodePayload(BaseModel):
    type: Literal["code"]
    language: str
    code: str
    description: str


class CompanyInfoPayload(BaseModel):
    """Dashboard for company info (Futunn scraper)."""
    type: Literal["company_info"]
    company_name: str
    symbol: str
    price: str
    change: str
    change_percent: str
    market_cap: str
    pe_ratio: str
    description: str
    stats: list[MetricCard] = []
    profile: dict[str, str] = Field(default_factory=dict)


class SectorItem(BaseModel):
    """Single sector entry in a sector heatmap."""
    sector: str
    change_percent: str
    link: str
    # Only present when source == "tradingview"
    market_cap: Optional[str] = None
    dividend_yield: Optional[str] = None
    volume: Optional[str] = None
    industries_count: Optional[str] = None
    stocks_count: Optional[str] = None
    perf_1w: Optional[str] = None
    perf_1m: Optional[str] = None
    perf_3m: Optional[str] = None
    perf_6m: Optional[str] = None
    perf_ytd: Optional[str] = None
    perf_1y: Optional[str] = None
    perf_5y: Optional[str] = None
    perf_10y: Optional[str] = None
    perf_all_time: Optional[str] = None


class SectorPayload(BaseModel):
    """Dashboard for sector heatmap analysis."""
    type: Literal["sector"]
    source: Literal["tradingview", "futunn", "yfinance"]
    interactive: bool  # True only when TradingView succeeded
    sectors: list[SectorItem]


# ── API Request / Response ────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    history: list[dict]
    mode: Literal["none", "market_discovery", "stock_deep_analysis"] = "none"


class ChatResponse(BaseModel):
    reply_text: str
    dashboard_payload: (
        MarketDiscoveryPayload | ChartPayload | CodePayload | CompanyInfoPayload | SectorPayload | None
    )


class ChatResponseV2(BaseModel):
    """Full pipeline response with thinking steps."""
    reply_text: str
    dashboard_payload: (
        MarketDiscoveryPayload | ChartPayload | CodePayload | CompanyInfoPayload | SectorPayload | None
    )
    thinking_steps: list[ThinkingStep] = Field(default_factory=list)
    mode_used: Literal["company_info", "sector_analysis", "none"] = "none"


# ── Frontend Log Payload ─────────────────────────────────────────────────────

class FrontendLogRequest(BaseModel):
    level: Literal["debug", "info", "warn", "error"]
    message: str
    stack: Optional[str] = None
    url: Optional[str] = None
    userAgent: Optional[str] = None
