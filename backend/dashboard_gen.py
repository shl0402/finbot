# backend/dashboard_gen.py
# Real data builders for CompanyInfo and Sector dashboards.
# Replaces the old mock data generator.

from models import (
    CompanyInfoPayload,
    SectorPayload,
    SectorItem,
    MetricCard,
    ChartPayload,
    ChartPoint,
    MarketDiscoveryPayload,
    CodePayload,
    RRScore,
)
from typing import Any, Literal


# ── Helpers ────────────────────────────────────────────────────────────────────

def _is_empty(val: Any) -> bool:
    """Return True for values that carry no useful information."""
    if val is None:
        return True
    s = str(val).strip()
    return s in ("", "N/A", "n/a", "None", "-", "—", "–", "null")


def _filter_stats(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict with empty/N/A entries removed."""
    return {k: v for k, v in raw.items() if not _is_empty(v)}


# Preferred display order for company stats (label -> key in Futunn scraper output)
# Keys must match the exact label text scraped from the Futunn HTML page.
PREFERRED_STATS = [
    ("Market Cap", "Market Cap"),
    ("P/E (TTM)", "P/E (TTM)"),
    ("P/E", "P/E"),
    ("Volume", "Volume"),
    ("52wk High", "52wk High"),
    ("52wk Low", "52wk Low"),
    ("Dividend Yield", "Dividend Yield"),
    ("Beta", "Beta"),
    ("Turnover", "Turnover"),
    ("Turnover Ratio", "Turnover Ratio"),
    ("Shs Float", "Shs Float"),
    ("Revenue", "Revenue"),
    ("Net Income", "Net Income"),
    ("EPS", "EPS"),
    ("EPS (TTM)", "EPS (TTM)"),
    ("Shares Float", "Shares Float"),
    ("Beta (1Y)", "Beta (1Y)"),
]


def _build_metric_cards(stats: dict[str, Any]) -> list[MetricCard]:
    """Convert a flat stats dict into a list of MetricCards, ordered by preference."""
    filtered = _filter_stats(stats)
    cards: list[MetricCard] = []

    # Add preferred stats first, in order
    for label, key in PREFERRED_STATS:
        if key in filtered and not _is_empty(filtered[key]):
            cards.append(MetricCard(label=label, value=str(filtered[key])))
            del filtered[key]

    # Add remaining stats (alphabetically) up to 12 total
    for key in sorted(filtered.keys()):
        if len(cards) >= 12:
            break
        val = filtered[key]
        cards.append(MetricCard(label=key, value=str(val)))

    return cards


# ── Company Info Builder ────────────────────────────────────────────────────────

def build_company_info_payload(data: dict[str, Any]) -> CompanyInfoPayload | None:
    """
    Build a CompanyInfoPayload from Futunn scraper output.

    Expected data shape (from futunn_company_info_scrawler):
    {
        "company_name": str,
        "price": str,
        "change_price": str,
        "change_percent": str,
        "description": str,
        "stats": { key: value, ... },
        "profile": { key: value, ... },
    }
    """
    if not data:
        return None

    company_name = data.get("company_name", "Unknown Company")
    symbol = data.get("symbol", "")
    price = data.get("price", "N/A")
    change = data.get("change_price", "N/A")
    change_percent = data.get("change_percent", "N/A")
    description = data.get("description", "")
    stats_raw = data.get("stats", {})
    profile_raw = data.get("profile", {})
    market_cap = str(data.get("market_cap", "N/A"))
    pe_ratio = str(data.get("pe_ratio", "N/A"))

    # Build metric cards from stats (filter out N/A / empty)
    stats = _filter_stats(stats_raw)
    metric_cards = _build_metric_cards(stats)

    # Profile dict — filter empties
    profile = _filter_stats(profile_raw)

    return CompanyInfoPayload(
        type="company_info",
        company_name=company_name,
        symbol=symbol,
        price=price,
        change=change,
        change_percent=change_percent,
        market_cap=market_cap,
        pe_ratio=pe_ratio,
        description=description,
        stats=metric_cards,
        profile=profile,
    )


def build_tradingview_company_info_payload(data: dict[str, Any]) -> CompanyInfoPayload | None:
    """
    Build a CompanyInfoPayload from TradingView scraper output.

    Expected data shape (from tradingview_stock_info_scrawler):
    {
        "symbol": "NASDAQ:NVDA",
        "name": "NVIDIA Corp",
        "price": {"current": "...", "currency": "...", "change_percent": "..."},
        "key_stats": {market_cap, pe_ratio, ...},
        "about": {sector, industry, ceo, headquarters, description, ...},
        "technical_analysis": "...",
        "analyst_rating": "...",
    }
    """
    if not data:
        return None

    name = data.get("name", "Unknown Company")
    symbol = data.get("symbol", "")
    price_data = data.get("price", {})
    key_stats = data.get("key_stats", {})
    about = data.get("about", {})

    current = price_data.get("current", "N/A")
    currency = price_data.get("currency", "")
    change_pct = price_data.get("change_percent", "N/A")
    price_str = f"{current} {currency}".strip() if currency else current

    market_cap = str(key_stats.get("market_cap", "N/A"))
    pe_ratio = str(key_stats.get("pe_ratio", "N/A"))
    description = about.get("description", "")
    sector = about.get("sector", "")
    industry = about.get("industry", "")

    stats_dict = {
        "Market Cap": market_cap,
        "P/E (TTM)": pe_ratio,
        "Sector": sector,
        "Industry": industry,
        "Beta (1Y)": key_stats.get("beta_1y", "N/A"),
        "EPS (TTM)": key_stats.get("basic_eps", "N/A"),
        "Revenue (FY)": key_stats.get("revenue_fy", "N/A"),
        "Net Income (FY)": key_stats.get("net_income_fy", "N/A"),
        "Shares Float": key_stats.get("shares_float", "N/A"),
        "Dividend Yield": key_stats.get("dividend_yield", "N/A"),
    }

    profile_dict = {
        "CEO": about.get("ceo", "N/A"),
        "Headquarters": about.get("headquarters", "N/A"),
        "Founded": about.get("founded", "N/A"),
        "IPO Date": about.get("ipo_date", "N/A"),
        "Website": about.get("website", "N/A"),
        "Technical Analysis": data.get("technical_analysis", "N/A"),
        "Analyst Rating": data.get("analyst_rating", "N/A"),
    }

    stats = _filter_stats(stats_dict)
    metric_cards = _build_metric_cards(stats)
    profile = _filter_stats(profile_dict)

    return CompanyInfoPayload(
        type="company_info",
        company_name=name,
        symbol=symbol,
        price=price_str,
        change="N/A",
        change_percent=change_pct,
        market_cap=market_cap,
        pe_ratio=pe_ratio,
        description=description,
        stats=metric_cards,
        profile=profile,
    )


# ── Sector Builder ─────────────────────────────────────────────────────────────

def build_sector_payload(
    raw_sectors: list[dict[str, Any]],
    source: str,
) -> SectorPayload | None:
    """
    Build a SectorPayload from scraper output.

    source must be one of "tradingview", "futunn", "yfinance".
    Sets interactive=True only for "tradingview".
    """
    if not raw_sectors:
        return None

    clean_source: Literal["tradingview", "futunn", "yfinance"]
    if source in ("tradingview", "futunn", "yfinance"):
        clean_source = source  # type: ignore[assignment]
    else:
        clean_source = "futunn"  # type: ignore[assignment]

    interactive = (clean_source == "tradingview")

    def _percent(val: Any) -> str:
        if val is None:
            return "N/A"
        return str(val).strip() or "N/A"

    def _opt_str(val: Any) -> str | None:
        if _is_empty(val):
            return None
        return str(val).strip()

    items: list[SectorItem] = []
    for raw in raw_sectors:
        item = SectorItem(
            sector=str(raw.get("sector", "Unknown")).strip(),
            change_percent=_percent(raw.get("change_percent")),
            link=str(raw.get("link", "")).strip() or "N/A",
        )

        # Fill optional fields only when they exist in the raw data
        if interactive:
            item.market_cap = _opt_str(raw.get("market_cap"))
            item.dividend_yield = _opt_str(raw.get("dividend_yield"))
            item.volume = _opt_str(raw.get("volume"))
            item.industries_count = _opt_str(raw.get("industries_count"))
            item.stocks_count = _opt_str(raw.get("stocks_count"))
            item.perf_1w = _opt_str(raw.get("perf_1w"))
            item.perf_1m = _opt_str(raw.get("perf_1m"))
            item.perf_3m = _opt_str(raw.get("perf_3m"))
            item.perf_6m = _opt_str(raw.get("perf_6m"))
            item.perf_ytd = _opt_str(raw.get("perf_ytd"))
            item.perf_1y = _opt_str(raw.get("perf_1y"))
            item.perf_5y = _opt_str(raw.get("perf_5y"))
            item.perf_10y = _opt_str(raw.get("perf_10y"))
            item.perf_all_time = _opt_str(raw.get("perf_all_time"))

        items.append(item)

    return SectorPayload(
        type="sector",
        source=clean_source,
        interactive=interactive,
        sectors=items,
    )


# ── Legacy mock builders (kept for backward compatibility) ─────────────────────

def generate(payload_type: str | None):
    """Legacy mock builder — kept so existing tests don't break."""
    import random
    import numpy as np
    from datetime import datetime, timedelta

    if payload_type == "metrics":
        return MarketDiscoveryPayload(
            type="metrics",
            symbol="MOCK",
            name="Mock Stock",
            metrics=[
                MetricCard(label="Expected Profit", value="15%"),
                MetricCard(label="Suggested Buy", value="$100"),
                MetricCard(label="Take Profit", value="$115"),
                MetricCard(label="Stop Loss", value="$90", delta="-10%", delta_color="inverse"),
                MetricCard(label="Win Rate", value="60%"),
            ],
            rr_score=RRScore(ratio="2.0:1", description="Good risk:reward"),
        )
    if payload_type == "chart":
        n = 30
        base = 100.0
        dates = [
            (datetime.today() - timedelta(days=n - 1 - i)).strftime("%Y-%m-%d")
            for i in range(n)
        ]
        np.random.seed(42)
        open_vals = (np.random.uniform(base * 0.93, base * 1.07, n)).tolist()
        close_vals = [o + random.uniform(-5, 5) for o in open_vals]
        high_vals = [max(o, c) + random.uniform(0, 4) for o, c in zip(open_vals, close_vals)]
        low_vals = [min(o, c) - random.uniform(0, 4) for o, c in zip(open_vals, close_vals)]
        chart_data = [
            ChartPoint(
                date=d, open=round(o, 2), high=round(h, 2),
                low=round(l, 2), close=round(c, 2),
            )
            for d, o, h, l, c in zip(dates, open_vals, high_vals, low_vals, close_vals)
        ]
        return ChartPayload(
            type="chart",
            symbol="MOCK",
            name="Mock Stock",
            chart_data=chart_data,
            key_stats=[MetricCard(label="RSI", value="55")],
        )
    if payload_type == "code":
        return CodePayload(
            type="code",
            language="python",
            code="# mock code",
            description="Mock code block",
        )
    return None
