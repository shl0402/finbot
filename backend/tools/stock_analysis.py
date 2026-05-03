#!/usr/bin/env python3
"""
Self-contained stock prediction tool — designed to be called by an LLM.

Pipeline:
  1. Scrape real-time news  (manager.run_scraper_manager, mode="futunn_news")
  2. Label via Gemini LLM   (google.genai SDK + response_schema, matching main.py)
  3. Score sentiment        (FinBERT / lexicon — same as sam_ontology.ipynb)
  4. Apply ontology        (competitor=invert, match=pass — same as sam_ontology.ipynb)
  5. Aggregate to daily    (sentiment_mean + news_count per day + lag features)
  6. Fetch price features  (price_feature_engine.get_price_features)
  7. Run ensemble model    (ensemble_models.ModelLoader: GBM + LSTM + stacking)

All imports are from within the tools/ directory.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, AsyncGenerator


import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ── Ensure tools/ is on the path so local imports work ──────────────────────
_TOOLS_DIR = Path(__file__).parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

# ── Local tool imports ───────────────────────────────────────────────────────
from manager import run_scraper_manager               # news scraping
from price_feature_engine import get_price_features   # price features
from ensemble_models import ModelLoader                       # ensemble model

# google-genai (structured LLM calls — matching main.py's SignalEnrichmentPipeline)
try:
    from google import genai
    from google.genai import types

    _GEMINI_SDK = True
except ImportError:
    _GEMINI_SDK = False
    genai = None
    types = None

# ── Configuration ────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    load_dotenv(env_path)
except ImportError:
    pass

API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash-lite"

# System prompt — hardcoded from config.yaml
SYSTEM_PROMPT = """You are an expert quantitative finance AI. Your task is to analyze financial news titles and map them to a specific structural ontology relative to a TARGET STOCK.

ONTOLOGY:
This ontology defines how news sentiment is dynamically translated into actionable trading signals for a specific TARGET STOCK. It maps the economic relationship between the entity mentioned in the news and the target.

0. Direct Entity Events (The "Self")
News explicitly regarding the target stock itself.
* 0.1 Direct Fundamental (Match): Earnings reports, guidance updates, product launches, or management changes directly at the target company.
* 0.2 Direct Regulatory/Legal (Match): The target company wins/loses a lawsuit, faces fines, or receives direct government approval.
* 0.3 Corporate Action (Match): Stock splits, buybacks, or dividend announcements.
* 0.4 Analyst/Brokerage Rating (Match): Upgrades, downgrades, price target adjustments, or initiation of coverage by investment banks and research firms.

1. Horizontal Relationships (Competitors & Peers)
Entities fighting for the same market share or capital.
* 1.1 Zero-Sum Catalyst (Invert): Competitor captures a finite resource (contract, patent, exclusive rights).
* 1.2 Sector Tailwind/Headwind (Match): A peer proves a macro trend that lifts/drags the whole sector.
* 1.3 Capacity/Supply Destruction (Invert): A peer suffers a factory fire, ban, or bankruptcy (Target gains market share).
* 1.4 Substitution Threat (Invert): An adjacent industry creates a cheaper/better alternative to the target's product.

2. Vertical Relationships (Supply Chain)
Shocks traveling up and down the flow of goods.
* 2.1 Upstream Breakthrough/Expansion (Match): Supplier invents a cheaper process or expands capacity.
* 2.2 Upstream Supply Shock (Match): Supplier faces shortages, strikes, or tariffs.
* 2.3 Downstream Demand Shock (Match): Major buyer sees a massive surge/drop in end-user sales.
* 2.4 Downstream Insolvency/Churn (Match): Major client goes bankrupt or switches to a competitor.

3. Strategic Relationships (Ecosystem)
Entities whose success is tied to the target without being direct suppliers.
* 3.1 Complementary Goods (Match): Products bought together (e.g., EVs and Charging Stations).
* 3.2 Strategic Partners/JV (Match): Explicit R&D, distribution, or marketing partnerships.

4. Market Microstructure & Capital Flows
News regarding the structural buying/selling of the stock, independent of company fundamentals.
* 4.1 Institutional Capital Flow (Match): Significant buying/selling by funds (e.g., Southbound Capital, Hedge Funds).
* 4.2 Index/ETF Inclusion (Match): The target is added to or removed from a major market index.

* 0.0 No Relation / Noise: The news does not fit the ontology, lacks actionable connection, or is purely retrospective summary.

INSTRUCTIONS:
1. Analyze the provided News Title relative to the Target Stock.
2. Extract the names of any companies explicitly mentioned into the 'related_company' array.
3. Determine the relationship ID using the ontology.
4. Evaluate 'fixed_sentiment_applicable': Because our downstream pipeline uses a "dumb" fixed sentiment model that scores the WHOLE text, you must determine if it is safe to apply.
   - Set to TRUE if the headline's overall tone clearly matches the direction of the catalyst.
   - Set to FALSE if the headline is mixed, highly complex, or talks about a competitor winning while the target is losing (a fixed sentiment model will score this near 0.0, which breaks our math).
5. Unknown Entity Protocol: If a company is mentioned that you do not recognize, and the text does not provide enough context to determine if they are a competitor, supplier, or partner to the Target Stock's sector, you MUST classify the relation_id as "0.0". Do not guess.

Output strictly as JSON:
{
  "chain_of_thought": "Explanation of the economic logic.",
  "related_company": ["Company A", "Company B"],
  "relation_id": "1.2",
  "fixed_sentiment_applicable": true,
  "confidence_score": 0.95
}"""


# ── LLM Labeler (matching main.py's SignalEnrichmentPipeline) ─────────────────

class LLMLabeler:
    """
    Labels news headlines via Gemini SDK using response_schema.
    Exactly matches main.py's SignalEnrichmentPipeline behavior.
    """

    RESPONSE_SCHEMA = {
        "type": "OBJECT",
        "properties": {
            "chain_of_thought": {"type": "STRING"},
            "related_company": {"type": "ARRAY", "items": {"type": "STRING"}},
            "relation_id": {"type": "STRING"},
            "fixed_sentiment_applicable": {"type": "BOOLEAN"},
            "confidence_score": {"type": "NUMBER"},
        },
        "required": [
            "chain_of_thought", "related_company", "relation_id",
            "fixed_sentiment_applicable", "confidence_score",
        ],
    }

    def __init__(self, api_key: str, model_name: str = GEMINI_MODEL, max_concurrent: int = 5):
        self.api_key = api_key
        self.model_name = model_name
        self._client = None
        self._semaphore = None
        self._config = None
        self._available = False
        self._init_error: str | None = None

        if not _GEMINI_SDK:
            self._init_error = "google-genai package not installed. Install with: pip install google-genai"
            print(f"[LLMLabeler] ERROR: {self._init_error}")
            return

        # Strip whitespace so key is not silently rejected due to trailing newline
        api_key = api_key.strip()

        if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
            self._init_error = "API key not set or still contains placeholder 'YOUR_GEMINI_API_KEY_HERE'. Set it at the top of test.py."
            print(f"[LLMLabeler] ERROR: {self._init_error}")
            return

        try:
            self._client = genai.Client(api_key=api_key)
            self._semaphore = asyncio.Semaphore(max_concurrent)
            self._config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=self.RESPONSE_SCHEMA,
            )
            self._available = True
            print(f"[LLMLabeler] Initialized successfully. Model: {model_name}")
        except Exception as e:
            self._init_error = f"Failed to initialize Gemini client: {e}"
            print(f"[LLMLabeler] ERROR: {self._init_error}")
            self._available = False

    def _check_ready(self) -> None:
        """Raise a RuntimeError if the labeler is not usable. Call at the top of label_news."""
        if not self._available:
            raise RuntimeError(
                f"[LLMLabeler] Cannot label news — {self._init_error or 'unknown error'}. "
                "Fix the issue above and re-run."
            )

    async def _label_one(self, item: dict, ticker: str, index: int, max_retries: int = 1) -> dict | None:
        prompt = (
            f"Target Stock: {ticker}\n"
            f"Target Sector: Unknown\n"
            f"News Title: {item.get('title', '')}"
        )

        # ── Attempt loop (1 initial + up to max_retries retries) ──────────────────
        last_error: Exception | None = None
        for attempt in range(1 + max_retries):
            try:
                async with self._semaphore:
                    response = await asyncio.wait_for(
                        self._client.aio.models.generate_content(
                            model=self.model_name,
                            contents=prompt,
                            config=self._config,
                        ),
                        timeout=30.0,
                    )
                llm_output = json.loads(response.text)
                item["relation_id"] = str(llm_output.get("relation_id", "0.0"))
                item["fixed_sentiment_applicable"] = bool(llm_output.get("fixed_sentiment_applicable", True))
                item["related_company"] = list(llm_output.get("related_company", []))
                item["chain_of_thought"] = str(llm_output.get("chain_of_thought", ""))
                item["confidence_score"] = float(llm_output.get("confidence_score", 0.5))
                item["llm_skipped"] = False
                print(f"  [{index}] OK: rel_id={item['relation_id']} | fixed_sentiment={item['fixed_sentiment_applicable']} "
                      f"| related={item['related_company']} | confidence={item['confidence_score']:.2f}")
                return item
            except asyncio.TimeoutError:
                last_error = None
                print(f"  [{index}] Attempt {attempt+1}: TIMEOUT (>30s).", end="")
                if attempt < max_retries:
                    print(" Retrying...")
                else:
                    print(" Skipping item.")
                break  # Don't retry timeouts
            except json.JSONDecodeError as e:
                last_error = None
                print(f"  [{index}] Attempt {attempt+1}: PARSE ERROR ({e}). Skipping item.")
                break
            except Exception as e:
                last_error = e
                err_type = type(e).__name__
                # Retry on 503 / 429 (rate limit) — transient errors
                if getattr(e, "code", None) in (503, 429) or "503" in str(e) or "429" in str(e):
                    print(f"  [{index}] Attempt {attempt+1}: {err_type} ({e}). Retrying...")
                    await asyncio.sleep(2)
                    continue
                # All other errors: skip immediately
                print(f"  [{index}] Attempt {attempt+1}: {err_type} ({e}). Skipping item.")
                break

        # ── All retries exhausted — mark as skipped ─────────────────────────────
        item["relation_id"] = "SKIP"
        item["fixed_sentiment_applicable"] = False
        item["related_company"] = []
        item["chain_of_thought"] = f"LLM failed after {1 + max_retries} attempt(s): {last_error}"
        item["confidence_score"] = 0.0
        item["llm_skipped"] = True
        return None

    async def label_news(self, news_items: list[dict], ticker: str) -> list[dict]:
        if not news_items:
            return []
        self._check_ready()  # Raises RuntimeError if LLM is not usable
        print(f"[LLMLabeler] Labeling {len(news_items)} headlines with Gemini...")
        tasks = [
            self._label_one(item.copy(), ticker=ticker, index=i + 1)
            for i, item in enumerate(news_items)
        ]
        results: list[dict | None] = await asyncio.gather(*tasks)
        # Filter out items the LLM failed to label
        labeled = [r for r in results if r is not None]
        skipped = len(results) - len(labeled)
        print(f"[LLMLabeler] Done. {len(labeled)} headlines labeled, {skipped} skipped.")
        return labeled


# ── Sentiment Analyzer (same as sam_ontology.ipynb Cell 0) ───────────────────

class SentimentAnalyzer:
    """
    FinBERT with TextBlob/lexicon fallback.
    Exactly matches sam_ontology.ipynb Cell 0 — same pos/neg word lists,
    same probability computation, same fallback logic.
    """

    def __init__(self):
        self.model = None
        self.pos_words = {
            "surge", "soar", "rally", "gain", "upgrade", "beat", "exceed",
            "growth", "profit", "bullish", "buy", "strong", "opportunity",
            "breakthrough", "positive", "record", "high", "rise", "increase",
            "outperform",
        }
        self.neg_words = {
            "drop", "fall", "decline", "downgrade", "miss", "below", "loss",
            "bearish", "sell", "weak", "risk", "warning", "negative", "low",
            "decrease", "plunge", "crash", "concern",
        }
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            print("[SentimentAnalyzer] Loading FinBERT...")
            self.tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
            self.model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.model.to(self.device)
            self.model.eval()
            self.labels = ["negative", "neutral", "positive"]
            print(f"[SentimentAnalyzer] FinBERT loaded on {self.device}")
        except Exception as e:
            print(f"[SentimentAnalyzer] FinBERT unavailable ({e}), using lexicon fallback.")
            self.model = None

    def get_sentiment(self, text: str) -> dict:
        if self.model is not None:
            try:
                import torch
                inputs = self.tokenizer(
                    text, return_tensors="pt", truncation=True, max_length=512
                )
                inputs = {k: v.to(self.device) for k, v in inputs.items()}
                with torch.no_grad():
                    probs = torch.nn.functional.softmax(
                        self.model(**inputs).logits, dim=-1
                    ).cpu().numpy()[0]
                return {
                    "sentiment": self.labels[int(probs.argmax())],
                    "score": float(probs[2] - probs[0]),
                    "positive_prob": float(probs[2]),
                    "negative_prob": float(probs[0]),
                    "neutral_prob": float(probs[1]),
                }
            except Exception:
                pass

        # Fallback (same logic as sam_ontology.ipynb)
        if pd.isna(text) or str(text).strip() == "":
            return {
                "sentiment": "neutral", "score": 0.0,
                "positive_prob": 0.0, "negative_prob": 0.0, "neutral_prob": 1.0,
            }
        text_lower = str(text).lower()
        pos_cnt = sum(1 for w in self.pos_words if w in text_lower)
        neg_cnt = sum(1 for w in self.neg_words if w in text_lower)
        total = pos_cnt + neg_cnt
        try:
            from textblob import TextBlob
            polarity = TextBlob(text).sentiment.polarity
        except Exception:
            polarity = 0.0
        if total == 0:
            final_polarity = polarity
        else:
            final_polarity = (pos_cnt - neg_cnt) / total
        if final_polarity > 0.1:
            sentiment = "positive"
        elif final_polarity < -0.1:
            sentiment = "negative"
        else:
            sentiment = "neutral"
        return {
            "sentiment": sentiment,
            "score": float(final_polarity),
            "positive_prob": float(max(0, final_polarity)),
            "negative_prob": float(max(0, -final_polarity)),
            "neutral_prob": float(1 - abs(final_polarity)),
        }


# ── Ontology Adjustment (same as sam_ontology.ipynb Cell 2) ──────────────────

def apply_ontology(items: list[dict], ticker: str) -> list[dict]:
    """
    Apply the financial knowledge graph ontology adjustment using Gemini's relation_id.
      - 1.1, 1.3, 1.4 -> invert sentiment score
      - 0.0 -> exclude/zero out (no relation)
      - otherwise -> pass through unchanged (match)
    """
    # The relation IDs that represent a zero-sum threat to the target stock
    INVERT_RELATIONS = {"1.1", "1.3", "1.4"}
    
    # We will build a new list to optionally drop the 0.0 items completely
    adjusted_items = []
    
    for item in items:
        rel_id = str(item.get("relation_id", "0.0")).strip()
        raw_score = float(item.get("raw_sentiment_score", 0.0))
        
        # 1. If it's 0.0 (No Relation / Noise), we completely ignore its sentiment score
        if rel_id in ("0.0", "0"):
            item["ontology_sentiment"] = 0.0
            
            # NOTE: If you want to completely hide 0.0 news from the dashboard 
            # and the daily mean math, you can type `continue` here instead of appending it.
            
        # 2. If it's a competitor stealing market share, invert it
        elif rel_id in INVERT_RELATIONS:
            item["ontology_sentiment"] = -raw_score
            
        # 3. All other relations (1.2, 2.x, 3.x, 4.x) pass through normally
        else:
            item["ontology_sentiment"] = raw_score
            
        adjusted_items.append(item)
        
    return adjusted_items


# ── Daily Sentiment Builder ───────────────────────────────────────────────────

class DailySentimentBuilder:
    """
    Aggregates labeled/scored news into daily sentiment.
    Produces a DataFrame with the 8 sentiment columns matching sentiment_store.py:
      sentiment_mean, sentiment_lag_1, sentiment_lag_2, sentiment_lag_3,
      news_count, news_lag_1, news_lag_2, news_lag_3
    """

    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    def _parse_date(self, date_str: str) -> datetime | None:
        if not date_str or date_str == "N/A":
            return None
        date_str = str(date_str).strip()

        # Relative / fuzzy strings (match before lowercasing so "April" is intact)
        date_lower = date_str.lower()
        if any(x in date_lower for x in ["hour", "minute", "just now", "ago"]):
            return datetime.now()
        if "day" in date_lower:
            m = re.search(r"(\d+)", date_str)
            if m:
                try:
                    return datetime.now() - timedelta(days=int(m.group(1)))
                except Exception:
                    pass
        if "week" in date_lower:
            m = re.search(r"(\d+)", date_str)
            if m:
                try:
                    return datetime.now() - timedelta(weeks=int(m.group(1)))
                except Exception:
                    pass

        # Explicit formats to try
        formats = [
            "%Y-%m-%d", "%Y/%m/%d",                     # 2026-04-29
            "%d/%m/%Y", "%m/%d/%Y",                   # 29/04/2026
            "%B %d, %Y", "%b %d, %Y",                 # April 29, 2026 / Apr 29, 2026
            "%d %B %Y", "%d %b %Y",                   # 29 April 2026
            "%B %d", "%b %d",                          # April 29 / Apr 29 (current year)
            "%d %B", "%d %b",                          # 29 April (current year)
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                # If no year was parsed, default to current year
                if dt.year == 1900:
                    dt = dt.replace(year=datetime.now().year)
                return dt
            except Exception:
                continue

        # Final fallback: dateparser
        try:
            import dateparser as _dp
            return _dp.parse(date_str)
        except Exception:
            pass
        return None

    def build(self, items: list[dict]) -> tuple[pd.DataFrame, dict]:
        """
        Build daily aggregation and return (sentiment_df, daily_summary).
        daily_summary maps date -> {"sentiment_mean": float, "news_count": int}
        """
        records = []
        for item in items:
            raw_time = item.get("time", "")
            dt = self._parse_date(raw_time)
            if dt is None:
                dt = datetime.now()
                print(f"       [DATE PARSE] Unparseable date: {repr(raw_time)} -> defaulting to today")
            # Defensive: ensure dt is a valid datetime (not pd.NaT or similar)
            if pd.isnull(dt):
                dt = datetime.now()
                print(f"       [DATE PARSE] Null date detected for {repr(raw_time)} -> defaulting to today")
            records.append({
                "date": dt.replace(hour=0, minute=0, second=0, microsecond=0),
                "sentiment_score": float(item.get("ontology_sentiment", 0.0)),
            })

        if not records:
            records = [{"date": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                        "sentiment_score": 0.0}]

        df = pd.DataFrame(records)
        daily_agg = df.groupby("date", as_index=False).agg(
            sentiment_mean=("sentiment_score", "mean"),
            news_count=("sentiment_score", "count"),
        ).sort_values("date").reset_index(drop=True)

        # Lag features (same as sentiment_store.py)
        for lag in [1, 2, 3]:
            daily_agg[f"sentiment_lag_{lag}"] = daily_agg["sentiment_mean"].shift(lag)
            daily_agg[f"news_lag_{lag}"] = daily_agg["news_count"].shift(lag)
        # Only drop rows where the core data columns are null (not lag cols,
        # which are NaN by design for the first 3 rows via shift())
        daily_agg = daily_agg.dropna(subset=["date", "sentiment_mean", "news_count"])

        sent_cols = ["sentiment_mean", "sentiment_lag_1", "sentiment_lag_2", "sentiment_lag_3",
                     "news_count", "news_lag_1", "news_lag_2", "news_lag_3"]

        # Pad to lookback days if needed
        if len(daily_agg) < self.lookback:
            padding_rows = self.lookback - len(daily_agg)
            pad_dates = [daily_agg["date"].min() - timedelta(days=i + 1) for i in range(padding_rows)]
            pad_data = {
                "date": pad_dates,
                "sentiment_mean": [0.0] * padding_rows,
                "news_count": [0] * padding_rows,
            }
            for lag in [1, 2, 3]:
                pad_data[f"sentiment_lag_{lag}"] = [0.0] * padding_rows
                pad_data[f"news_lag_{lag}"] = [0] * padding_rows
            pad_df = pd.DataFrame(pad_data)
            daily_agg = pd.concat([pad_df, daily_agg], ignore_index=True)
        elif len(daily_agg) > self.lookback:
            daily_agg = daily_agg.tail(self.lookback).reset_index(drop=True)

        # Daily summary dict for output
        daily_summary = {}
        for _, r in daily_agg.iterrows():
            date_val = r["date"]
            # Skip rows with null/NaT dates (shouldn't happen after the guard above, but be safe)
            if pd.isnull(date_val):
                print(f"       [DATE AGG] Skipping row with NaT date")
                continue
            date_key = str(date_val.date())
            daily_summary[date_key] = {
                "sentiment_mean": round(float(r["sentiment_mean"]), 4),
                "news_count": int(r["news_count"]),
            }

        return daily_agg[sent_cols].reset_index(drop=True), daily_summary


# ── Tool Function ─────────────────────────────────────────────────────────────

async def run_prediction(
    ticker: str,
    num_news: int = 30,
) -> AsyncGenerator[dict, None]:
    """
    Self-contained async-generator prediction tool — yields step events as they
    complete, then yields the final result dict.

    Each yielded item is one of:
      - {"step": <name>, "status": "start"|"complete"|"failed", "message": "...", ...kwargs}
      - ("result", <result_dict>)  — the final return value

    Example usage:
      async for event in run_prediction("AAPL"):
          if event[0] == "result":
              result = event[1]
          else:
              print(f"[{event['step']}] {event['status']} — {event['message']}")
    """
    print(f"\n{'='*60}")
    print(f"  [TOOL] Running prediction for ticker: {ticker}")
    print(f"{'='*60}\n")

    def _emit(step: str, status: str, **kwargs) -> dict:
        return {"step": step, "status": status, **kwargs}

    from datetime import datetime as _dt
    pipeline_start = _dt.utcnow().isoformat()

    # ── Step 1: Scrape news ───────────────────────────────────────────────
    yield _emit("news_scraping", "start",
         message="Scraping news via Futunn (last 20 days, max 2/day)...")
    print(f"[news_scraping] start  Scraping news via Futunn (last 20 days, max 2/day)...")
    raw_news = await asyncio.to_thread(
        run_scraper_manager, stock_name=ticker, mode="futunn_news_days",
        num_days=20, max_per_day=2
    )
    news_items: list[dict] = []
    if raw_news and isinstance(raw_news, list):
        for item in raw_news:
            news_items.append({
                "title":             item.get("title", ""),
                "time":              item.get("time", ""),
                "source":            item.get("source", ""),
                "link":              item.get("link", ""),
                "short_description": item.get("short_description", ""),
                "parsed_date":       item.get("parsed_date_str", ""),
            })
    yield _emit("news_scraping", "complete",
         message=f"Scraped {len(news_items)} items",
         count=len(news_items))
    print(f"[news_scraping] complete  Scraped {len(news_items)} items  count={len(news_items)}")

    # ── Step 2: LLM labeling ───────────────────────────────────────────────
    yield _emit("llm_labeling", "start",
         message=f"Labeling {len(news_items)} headlines via Gemini...")
    print(f"\n[llm_labeling] start  Labeling {len(news_items)} headlines via Gemini...")
    labeler = LLMLabeler(API_KEY)
    labeled = await labeler.label_news(news_items, ticker)
    yield _emit("llm_labeling", "complete",
         message=f"Labeled {len(labeled)} headlines",
         count=len(labeled))
    print(f"[llm_labeling] complete  Labeled {len(labeled)} headlines  count={len(labeled)}")

    # ── Step 3: Sentiment scoring ─────────────────────────────────────────
    yield _emit("sentiment", "start",
         message="Scoring sentiment (FinBERT / lexicon)...")
    print(f"\n[sentiment] start  Scoring sentiment (FinBERT / lexicon)...")
    analyzer = SentimentAnalyzer()
    for item in labeled:
        sent = analyzer.get_sentiment(item["title"])
        item["sentiment_label"]      = sent["sentiment"]
        item["raw_sentiment_score"]  = sent["score"]
        item["positive_prob"]        = sent["positive_prob"]
        item["negative_prob"]        = sent["negative_prob"]
        item["neutral_prob"]         = sent["neutral_prob"]
    yield _emit("sentiment", "complete",
         message=f"Scored {len(labeled)} items")
    print(f"[sentiment] complete  Scored {len(labeled)} items")

    # ── Step 4: Ontology adjustment ───────────────────────────────────────
    yield _emit("ontology", "start",
         message="Applying ontology adjustment (competitor=invert)...")
    print(f"\n[ontology] start  Applying ontology adjustment (competitor=invert)...")
    adjusted = apply_ontology(labeled, ticker)
    yield _emit("ontology", "complete",
         message=f"Adjusted {len(adjusted)} items",
         count=len(adjusted))
    print(f"[ontology] complete  Adjusted {len(adjusted)} items  count={len(adjusted)}")

    # ── Step 5: Daily aggregation ─────────────────────────────────────────
    yield _emit("daily_agg", "start",
         message="Building daily sentiment features (20-day lookback)...")
    print(f"\n[daily_agg] start  Building daily sentiment features (20-day lookback)...")
    builder = DailySentimentBuilder(lookback=20)
    sent_df, daily_summary = builder.build(adjusted)
    sent_df_dict = sent_df.to_dict(orient="records")
    parsed_dates = sorted(daily_summary.keys())
    latest_date  = parsed_dates[-1] if parsed_dates else None
    yield _emit("daily_agg", "complete",
         message=f"Built {len(parsed_dates)} daily rows",
         date_range=f"{parsed_dates[0] if parsed_dates else 'N/A'} → {latest_date or 'N/A'}",
         dates=parsed_dates)
    print(f"[daily_agg] complete  Built {len(parsed_dates)} daily rows  "
          f"date_range={parsed_dates[0] if parsed_dates else 'N/A'} → {latest_date or 'N/A'}")

    # ── Step 6: Price features ────────────────────────────────────────────
    yield _emit("price_fetch", "start",
         message="Fetching price features via yfinance...")
    print(f"\n[price_fetch] start  Fetching price features via yfinance...")
    try:
        from price_feature_engine import format_ticker
        raw_ticker = format_ticker(ticker)
        raw_data = yf.download(raw_ticker, period="6mo", progress=False)
        if not raw_data.empty:
            raw_dates = (
                pd.to_datetime(raw_data.index)
                .strftime("%Y-%m-%d")
                .tolist()
            )
        else:
            raw_dates = []

        price_df = get_price_features(ticker, lookback=20, fetch_days=100)
        price_cols = ["close", "Volume", "returns", "volatility_10d", "volume_change",
                      "price_range", "RSI", "MACD", "vwap", "hsi_volatility"]
        price_summary = {col: round(float(price_df[col].iloc[-1]), 4) for col in price_cols}
        price_df_dict = price_df.to_dict(orient="records")
        # Use the last N raw dates matching the lookback length
        price_dates = raw_dates[-len(price_df_dict):] if raw_dates else []

        # Extract OHLCV data from raw_data for the candlestick chart.
        # Flatten MultiIndex columns (yfinance returns (Price, Ticker) tuples).
        _ohlcv_df = raw_data.copy()
        if isinstance(_ohlcv_df.columns, pd.MultiIndex):
            _ohlcv_df.columns = _ohlcv_df.columns.get_level_values(0)
        _ohlcv_df.columns = [c.lower() if c != 'Volume' else 'volume' for c in _ohlcv_df.columns]
        _ohlcv_df = _ohlcv_df.reset_index()
        if 'date' not in _ohlcv_df.columns and 'Date' in _ohlcv_df.columns:
            _ohlcv_df.rename(columns={'Date': 'date'}, inplace=True)
        if 'date' in _ohlcv_df.columns:
            _ohlcv_df['date'] = pd.to_datetime(_ohlcv_df['date']).dt.strftime('%Y-%m-%d')
        _ohlcv_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
        _ohlcv_available = [c for c in _ohlcv_cols if c in _ohlcv_df.columns]
        _ohlcv_last = _ohlcv_df[_ohlcv_available].iloc[-len(price_df_dict):].reset_index(drop=True)
        ohlcv_data = _ohlcv_last.to_dict(orient="records")
        # Round numeric values for cleaner JSON
        for row in ohlcv_data:
            for k, v in row.items():
                if isinstance(v, float):
                    row[k] = round(v, 4)
                elif isinstance(v, (int, np.integer)):
                    row[k] = int(v)

        yield _emit("price_fetch", "complete",
             message=f"Fetched {len(price_df)} price rows",
             rows=len(price_df),
             latest_close=price_summary["close"])
        print(f"[price_fetch] complete  Fetched {len(price_df)} price rows  "
              f"latest_close={price_summary['close']}")
    except Exception as e:
        yield _emit("price_fetch", "failed",
             message=f"Price fetch failed: {e}")
        print(f"[price_fetch] failed  {e}")
        raise

    # ── Step 7: Ensemble model prediction ─────────────────────────────────
    yield _emit("model", "start",
         message="Running ensemble model (GBM + LSTM + stacking)...")
    print(f"\n[model] start  Running ensemble model (GBM + LSTM + stacking)...")
    try:
        loader = ModelLoader()
        prob, signal = loader.predict_from_features(price_df, sent_df)
        yield _emit("model", "complete",
             message=f"Prediction: {signal} ({prob:.4f})",
             probability_up=round(float(prob), 4),
             signal=signal)
        print(f"[model] complete  Prediction: {signal} ({prob:.4f})  "
              f"probability_up={round(float(prob), 4)}  signal={signal}")
    except Exception as e:
        yield _emit("model", "failed",
             message=f"Model prediction failed: {e}")
        print(f"[model] failed  {e}")
        raise

    # ── Assemble full result ───────────────────────────────────────────────
    result = {
        "ticker": ticker,
        "metadata": {
            "pipeline_start":    pipeline_start,
            "pipeline_end":      _dt.utcnow().isoformat(),
            "news_scraped":      len(news_items),
            "headlines_labeled": len(labeled),
            "daily_rows":        len(sent_df),
            "price_rows":        len(price_df),
            "lookback_days":     20,
        },
        "raw_news": [
            {
                "title":             n["title"],
                "time":              n["time"],
                "source":            n["source"],
                "link":              n["link"],
                "short_description": n["short_description"],
                "parsed_date":       n["parsed_date"],
            }
            for n in news_items
        ],
        "news_items": [
            {
                "title":                      item["title"],
                "time":                       item["time"],
                "source":                     item["source"],
                "link":                       item["link"],
                "short_description":            item["short_description"],
                "parsed_date":               item.get("parsed_date", ""),
                "relation_id":                item["relation_id"],
                "fixed_sentiment_applicable": item["fixed_sentiment_applicable"],
                "related_company":           item["related_company"],
                "chain_of_thought":           item["chain_of_thought"],
                "confidence_score":         float(item["confidence_score"]),
                "sentiment_label":           item["sentiment_label"],
                "raw_sentiment_score":       round(float(item["raw_sentiment_score"]), 4),
                "positive_prob":             round(float(item["positive_prob"]), 4),
                "negative_prob":             round(float(item["negative_prob"]), 4),
                "neutral_prob":              round(float(item["neutral_prob"]), 4),
                "ontology_sentiment":         round(float(item["ontology_sentiment"]), 4),
            }
            for item in adjusted
        ],
        "daily_sentiment":  daily_summary,
        "sentiment_df_dict": sent_df_dict,
        "price_df_dict":    price_df_dict,
        "price_dates":      price_dates,
        "price_summary":    price_summary,
        "ohlcv_data":      ohlcv_data,
        "model_prediction": {
            "probability_up": round(float(prob), 4),
            "signal": signal,
        },
        "prediction_bar": {
            "signal": signal,
            "probability_up": round(float(prob), 4),
        },
    }

    print(f"\n{'='*60}")
    print(f"  [TOOL] RESULT: {signal}  (probability_up = {prob:.4f})")
    print(f"{'='*60}\n")
    yield _emit("done", "complete",
         probability_up=round(float(prob), 4),
         signal=signal)
    yield ("result", result)


# ── __main__ ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Stock prediction tool.")
    parser.add_argument("--ticker", "-t", type=str, default="1810",
                        help="Stock ticker (default: 1810 = Xiaomi)")
    parser.add_argument("--num-news", "-n", type=int, default=30,
                        help="Max news items to label (default 30)")
    parser.add_argument("--progress", action="store_true",
                        help="Show structured progress events on stderr as JSON")
    parser.add_argument("--json-output", action="store_true",
                        help="Output full result as JSON to stdout (suppresses pretty-print)")
    args = parser.parse_args()

    ticker = args.ticker.strip()
    if not ticker:
        print("Error: --ticker cannot be empty.")
        import sys
        sys.exit(1)

    try:
        async def run_and_print():
            result = None
            async for event in run_prediction(ticker, num_news=args.num_news):
                if isinstance(event, tuple) and event[0] == "result":
                    result = event[1]
                else:
                    step = event.get("step", "?")
                    status = event.get("status", "?")
                    msg = event.get("message", "")
                    count = event.get("count")
                    prob = event.get("probability_up")
                    signal = event.get("signal", "")
                    print(f"[{step}] {status}  {msg}", file=sys.stderr)
                    if count is not None:
                        print(f"       count={count}", file=sys.stderr)
                    if prob is not None:
                        print(f"       probability_up={prob:.4f}  signal={signal}", file=sys.stderr)
            return result

        result = asyncio.run(run_and_print())

        if args.json_output:
            # Pure JSON — for programmatic consumption (backend → frontend)
            print(json.dumps(result, indent=2, default=str))
        else:
            # Human-readable summary
            print("\n" + "=" * 60)
            print("  TOOL OUTPUT SUMMARY")
            print("=" * 60)

            mp = result["model_prediction"]
            print(f"\n[Model Prediction]")
            print(f"  Ticker:         {result['ticker']}")
            print(f"  Signal:         {mp['signal']}")
            print(f"  Probability UP: {mp['probability_up']}")

            print(f"\n[Metadata]")
            m = result["metadata"]
            print(f"  news_scraped={m['news_scraped']}  "
                  f"labeled={m['headlines_labeled']}  "
                  f"daily_rows={m['daily_rows']}  "
                  f"price_rows={m['price_rows']}")

            print(f"\n[Price Summary]")
            ps = result["price_summary"]
            print(f"  close={ps['close']} | volume={ps['Volume']} | "
                  f"returns={ps['returns']:.4f}")
            print(f"  volatility_10d={ps['volatility_10d']:.4f} | "
                  f"RSI={ps['RSI']:.2f} | MACD={ps['MACD']:.4f}")

            print(f"\n[News Items] ({len(result['news_items'])} total)")
            for i, n in enumerate(result["news_items"]):
                print(f"\n  [{i+1}] {n['title'][:100]}")
                print(f"       time={n['time']} | source={n['source']}")
                print(f"       relation_id={n['relation_id']} | "
                      f"fixed_sentiment={n['fixed_sentiment_applicable']}")
                print(f"       related_company={n['related_company']}")
                print(f"       sentiment={n['sentiment_label']} | "
                      f"raw_score={n['raw_sentiment_score']} | "
                      f"ontology_score={n['ontology_sentiment']}")
                print(f"       confidence={n['confidence_score']}")
                print(f"       chain_of_thought={n['chain_of_thought'][:120]}")

            print(f"\n[Daily Sentiment] ({len(result['daily_sentiment'])} days)")
            for date, vals in sorted(result["daily_sentiment"].items(), reverse=True):
                print(f"  {date}: sentiment_mean={vals['sentiment_mean']:.4f}  "
                      f"news_count={vals['news_count']}")

            print(f"\n[Sentiment DataFrame rows] ({len(result['sentiment_df_dict'])} rows)")
            print(f"[Price DataFrame rows] ({len(result['price_df_dict'])} rows)")
            print(f"[Raw News] ({len(result['raw_news'])} items)")

            print("\n[Full JSON output available in result dict for LLM tool calling]")
            print("Prediction completed successfully.")

    except Exception as e:
        import traceback
        print(f"\n[ERROR] Tool execution failed: {e}")
        traceback.print_exc()
        import sys
        sys.exit(1)
