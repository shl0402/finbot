# backend/chat_service.py
#
# FinBot pipeline:
#   1. Intent Routing  — Gemini decides: company_info | sector_analysis | none
#   2. Tool Execution  — run scrapers (with fallback chains)
#   3. Response        — Gemini generates investment advice with tool context
#
# Thinking steps are accumulated throughout and returned in the response.
# All operations are logged via named loggers under "finbot.*".

import os
import re
import sys
import time

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Optional

import requests
import yaml
from dotenv import load_dotenv

from models import (
    ChatRequest,
    ChatResponseV2,
    ChatResponse,
    ThinkingStep,
    CompanyInfoPayload,
    SectorPayload,
)
from dashboard_gen import (
    build_company_info_payload,
    build_tradingview_company_info_payload,
    build_sector_payload,
    build_stock_analysis_payload,
)

# ── Env ────────────────────────────────────────────────────────────────────────

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}"
    f":generateContent?key={GEMINI_API_KEY}"
)

# ── Loggers ────────────────────────────────────────────────────────────────────

log_router = logging.getLogger("finbot.router")      # intent routing decisions
log_tools  = logging.getLogger("finbot.tools")       # scraper calls
log_respond = logging.getLogger("finbot.responder")   # response generation
log_pipe  = logging.getLogger("finbot.pipeline")     # general pipeline flow


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_step(
    step_num: int,
    phase: str,
    status: str,
    content: str,
    tool_used: str | None = None,
    tool_result_preview: str | None = None,
) -> ThinkingStep:
    return ThinkingStep(
        step_number=step_num,
        phase=phase,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        content=content,
        tool_used=tool_used,
        tool_result_preview=tool_result_preview,
    )


def _gen_content(
    prompt: str,
    system_instruction: str | None = None,
    temperature: float = 0.3,
) -> str:
    """Call Gemini API and return the text of the first candidate."""
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        raise RuntimeError(
            "GEMINI_API_KEY is not set. "
            "Please add your key to backend/.env"
        )

    contents = [{"parts": [{"text": prompt}]}]

    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 8192,
        },
    }

    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }

    log_respond.debug("Calling Gemini — prompt length: %d chars", len(prompt))
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.post(
                GEMINI_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=60,
            )
        except requests.exceptions.RequestException as exc:
            log_respond.warning(
                "Gemini request attempt %d/3 failed (network error): %s",
                attempt + 1, exc,
            )
            last_exc = exc
            if attempt < 2:
                time.sleep(1.5 ** attempt)
            continue

        if resp.status_code == 200:
            break

        is_server_error = 500 <= resp.status_code < 600
        log_respond.warning(
            "Gemini API attempt %d/3 returned %d: %s (server_error=%s)",
            attempt + 1, resp.status_code, resp.text[:200], is_server_error,
        )
        last_exc = RuntimeError(f"Gemini API returned {resp.status_code}: {resp.text}")

        if not is_server_error or attempt >= 2:
            break
        time.sleep(1.5 ** attempt)

    else:
        # all 3 attempts exhausted
        log_respond.error("Gemini API failed after 3 attempts")
        raise RuntimeError("Gemini API failed after 3 attempts") from last_exc

    if resp.status_code != 200:
        log_respond.error("Gemini API error %d: %s", resp.status_code, resp.text)
        raise RuntimeError(f"Gemini API returned {resp.status_code}: {resp.text}")

    data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")

    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    if not parts:
        raise RuntimeError("Gemini candidate has no parts")

    return parts[0].get("text", "")


def _parse_json_from_text(text: str) -> dict[str, Any]:
    """Extract the first JSON object from mixed text ( Gemini sometimes wraps JSON in markdown)."""
    # Try to find a code block first
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Try parsing the whole text as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Last resort: try to extract JSON from anywhere in the string
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    return {}


def _truncate_preview(data: Any, max_len: int = 200) -> str:
    """Short string preview of tool result for thinking step display."""
    s = json.dumps(data, ensure_ascii=False)
    if len(s) <= max_len:
        return s
    return s[:max_len] + "..."


def _truncate_tool_data(data: dict, max_len: int = 3000) -> str:
    """
    Truncate tool_data JSON for the response prompt, cutting at safe JSON boundaries
    (field ends) so the AI always receives valid JSON.
    """
    if not isinstance(data, dict):
        return _truncate_preview(data, max_len)

    s = json.dumps(data, ensure_ascii=False)
    if len(s) <= max_len:
        return s

    # Keep the most important fields: model_prediction, price_summary, metadata
    priority_keys = ["model_prediction", "price_summary", "metadata", "ticker"]
    result: dict = {}
    remaining = max_len

    for key in priority_keys:
        if key in data:
            val_str = json.dumps({key: data[key]}, ensure_ascii=False)
            if len(val_str) + 2 <= remaining:  # +2 for outer braces
                result[key] = data[key]
                remaining -= len(val_str)

    # Add a note about truncated data
    s_result = json.dumps(result, ensure_ascii=False)
    if len(s_result) + 40 < max_len:
        s_result = s_result[:-1] + f', "_truncated": true, "_original_len": {len(s)}}}'
    return s_result


# ── Intent Routing ──────────────────────────────────────────────────────────────

def route_intent(user_message: str) -> dict[str, Any]:
    """
    Use Gemini to classify the user's intent.
    Returns dict with: mode, stock_name, sector_name, reasoning
    """
    log_router.info("Routing intent for: %s", user_message[:120])
    try:
        raw = _gen_content(
            prompt=ROUTING_PROMPT + user_message,
            system_instruction=SYSTEM_ROUTING,
            temperature=0.1,
        )
        log_router.debug("Routing raw response: %s", raw[:500])

        parsed = _parse_json_from_text(raw)
        mode = parsed.get("mode", "none")
        if mode not in ("company_info", "sector_analysis", "stock_analysis", "none"):
            mode = "none"

        result = {
            "mode": mode,
            "stock_name": parsed.get("stock_name", "").strip(),
            "sector_name": parsed.get("sector_name", "").strip(),
            "reasoning": parsed.get("reasoning", "").strip(),
        }
        log_router.info(
            "Route decision: mode=%s stock=%s sector=%s reason=%s",
            result["mode"], result["stock_name"], result["sector_name"], result["reasoning"],
        )
        return result

    except Exception as exc:
        log_router.exception("Intent routing failed — defaulting to none: %s", exc)
        return {"mode": "none", "stock_name": "", "sector_name": "", "reasoning": "error"}


# ── Tool Execution ──────────────────────────────────────────────────────────────

def _infer_exchange(mapped_value: str) -> str:
    """
    Infer which scraper to use based on the mapped stock code format.

    - Mappings ending in -HK → Futunn (HK stocks use Futunn)
    - Mappings ending in -US → TradingView (US stocks only exist on TradingView)
    - Mappings with EXCHANGE-TICKER format → TradingView
    - Anything else → Treat as Futunn (default)
    """
    import re
    if not mapped_value or mapped_value == mapped_value.upper():
        return "futunn"
    if re.search(r'-[A-Z]{2}$', mapped_value):
        suffix = mapped_value[-3:].upper()
        if suffix in ("-US", "-UK", "-EU", "-DE", "-FR", "-JP", "-AU"):
            return "tradingview"
        return "futunn"
    if "-" in mapped_value:
        prefix = mapped_value.split("-")[0].upper()
        if prefix in ("NASDAQ", "NYSE", "AMEX", "LSE", "TSX", "ASX"):
            return "tradingview"
    return "futunn"


async def _run_company_info_chain(stock_name: str) -> tuple[dict, str]:
    """
    Company info scraper chain with exchange-aware routing.

    Flow:
      1. Map stock_name to both Futunn and TradingView codes via mapping files.
      2. Infer which exchange the company belongs to from the Futunn mapping.
         - HK stocks → use Futunn
         - US/Global stocks → use TradingView
      3. If primary scraper fails, fall back to the other platform.

    Returns (result, source_tag) where source_tag is "futunn" or "tradingview".

    Playwright scrapers use sync API, so they are offloaded to a thread pool via
    asyncio.to_thread() to avoid blocking the event loop.
    """
    from tools.manager import get_mapped_entity

    log_tools.info("Company info chain for: %s", stock_name)

    futunn_mapped = get_mapped_entity(stock_name, "futunn.com")
    tv_mapped = get_mapped_entity(stock_name, "tradingview.com")

    inferred = _infer_exchange(futunn_mapped)
    log_tools.info("Mapped '%s' → Futunn:'%s' TV:'%s' → inferred=%s",
                   stock_name, futunn_mapped, tv_mapped, inferred)

    primary_mode = "futunn_info" if inferred == "futunn" else "tradingview_info"
    fallback_mode = "tradingview_info" if inferred == "futunn" else "futunn_info"

    tried = []

    for scraper_mode in [primary_mode, fallback_mode]:
        tried.append(scraper_mode)
        result = await asyncio.to_thread(_try_company_scraper, stock_name, scraper_mode)
        if result and isinstance(result, dict) and (result.get("company_name") or result.get("name")):
            source = "futunn" if scraper_mode == "futunn_info" else "tradingview"
            log_tools.info("%s company info SUCCESS", source)
            return result, source
        source = "futunn" if scraper_mode == "futunn_info" else "tradingview"
        log_tools.warning("%s returned empty data — trying fallback", source)

    log_tools.error("All company info scrapers failed for '%s': tried=%s", stock_name, tried)
    return {}, "none"


def _try_company_scraper(stock_name: str, mode: str) -> dict:
    """
    Call run_scraper_manager for a given mode and return the raw result.
    Returns empty dict on failure.
    """
    from tools.manager import run_scraper_manager
    try:
        return run_scraper_manager(stock_name, mode) or {}
    except Exception as exc:
        log_tools.exception("%s failed: %s", mode, exc)
        return {}


async def _run_sector_chain() -> tuple[list, str]:
    """
    Try sector scrapers in order: TradingView -> Futunn -> YFinance.
    Returns (result_list, source_tag).

    Playwright scrapers use sync API, so they are offloaded to a thread pool via
    asyncio.to_thread() to avoid blocking the event loop.
    """
    from tools.manager import run_scraper_manager

    try:
        log_tools.info("Trying TradingView sector scraper...")
        result = await asyncio.to_thread(run_scraper_manager, "dummy", "tradingview_sectors")
        if result and isinstance(result, list) and len(result) > 0:
            log_tools.info("TradingView sectors SUCCESS — %d sectors", len(result))
            return result, "tradingview"
        log_tools.warning("TradingView returned empty — trying Futunn next")

        log_tools.info("Trying Futunn sector scraper...")
        result = await asyncio.to_thread(run_scraper_manager, "dummy", "futunn_sectors")
        if result and isinstance(result, list) and len(result) > 0:
            log_tools.info("Futunn sectors SUCCESS — %d sectors", len(result))
            return result, "futunn"
        log_tools.warning("Futunn returned empty — trying YFinance next")

        log_tools.info("Trying YFinance sector scraper...")
        result = await asyncio.to_thread(run_scraper_manager, "dummy", "yfinance_sectors")
        if result and isinstance(result, list) and len(result) > 0:
            log_tools.info("YFinance sectors SUCCESS — %d sectors", len(result))
            return result, "yfinance"
        log_tools.error("All sector scrapers failed")

    except Exception as exc:
        log_tools.exception("Sector chain FAILED: %s", exc)

    return [], "none"


async def _run_stock_analysis_chain(
    stock_name: str,
) -> AsyncGenerator[tuple[dict, str, dict] | tuple[str, dict], None]:
    """
    Async generator that yields pipeline steps as they complete, then yields the
    final result.

    Yields:
      - ("step", step_dict): a real-time pipeline step
      - ("result", (result_dict, source_tag)): the final result

    Usage:
        async for event in _run_stock_analysis_chain("AAPL"):
            if event[0] == "result":
                result, source = event[1]
            else:
                step = event[1]  # {"step": "...", "status": "...", "message": "..."}
    """
    from tools.manager import get_mapped_entity
    from tools import stock_analysis as sa

    log_tools.info("Stock analysis chain for: %s", stock_name)

    futunn_mapped = get_mapped_entity(stock_name, "futunn.com")
    ticker = futunn_mapped.strip()
    if not ticker or ticker == stock_name:
        ticker = stock_name.strip()

    log_tools.info("Stock analysis using ticker: %s (from '%s')", ticker, stock_name)

    try:
        async for event in sa.run_prediction(ticker, num_news=30):
            if isinstance(event, tuple) and event[0] == "result":
                result = event[1]
                log_tools.info(
                    "Stock analysis pipeline SUCCESS for %s — signal=%s prob=%.4f",
                    ticker, result.get("model_prediction", {}).get("signal", "?"),
                    result.get("model_prediction", {}).get("probability_up", 0.0)
                )
                yield ("result", (result, "stock_analysis"))
            else:
                # event is a step dict: {"step": "...", "status": "...", "message": "..."}
                yield ("step", event)

    except Exception as exc:
        log_tools.exception("Stock analysis chain FAILED for %s: %s", ticker, exc)
        yield ("step", {"step": "model", "status": "failed", "message": str(exc)})
        yield ("result", ({}, "none"))


# ── Load Prompts from YAML ──────────────────────────────────────────────────────

_PROMPTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts.yaml")

def _load_prompts() -> dict:
    with open(_PROMPTS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

_PROMPTS = _load_prompts()

# ── Intent Routing ────────────────────────────────────────────────────────────

ROUTING_PROMPT   = _PROMPTS["routing"]["prompt"]
SYSTEM_ROUTING   = _PROMPTS["routing"]["system"]

# ── Response Generation ─────────────────────────────────────────────────────────

SYSTEM_RESPONSE  = _PROMPTS["system_response"]
RESPONSE_TEMPLATES = _PROMPTS["response_templates"]


def generate_response(
    mode: str,
    user_message: str,
    tool_data: Any,
    tool_source: str,
    conversation_history: list[dict],
) -> str:
    """Build context + call Gemini for the final response."""
    log_respond.info("Generating response — mode=%s", mode)

    history_text = ""
    if conversation_history:
        lines = []
        for msg in conversation_history[-6:]:  # last 6 turns
            role = msg.get("role", "?").capitalize()
            content = msg.get("content", "")
            if content:
                lines.append(f"{role}: {content[:300]}")
        history_text = "\n".join(lines)

    if mode == "company_info":
        tool_str = _truncate_preview(tool_data, max_len=3000)
        prompt = RESPONSE_TEMPLATES["company_info"].format(
            tool_data=tool_str,
            user_message=user_message,
        )
    elif mode == "sector_analysis":
        tool_str = _truncate_preview(tool_data, max_len=3000)
        prompt = RESPONSE_TEMPLATES["sector_analysis"].format(
            source=tool_source.upper(),
            tool_data=tool_str,
            user_message=user_message,
        )
    elif mode == "stock_analysis":
        tool_str = _truncate_tool_data(tool_data, max_len=3000)
        prompt = RESPONSE_TEMPLATES["stock_analysis"].format(
            tool_data=tool_str,
            user_message=user_message,
        )
    else:
        prompt = RESPONSE_TEMPLATES["none"].format(user_message=user_message)

    if history_text:
        prompt = f"Recent conversation:\n{history_text}\n\n---\n\n{prompt}"

    try:
        response = _gen_content(prompt=prompt, system_instruction=SYSTEM_RESPONSE)
        log_respond.info("Response generated — %d chars", len(response))
        return response
    except Exception as exc:
        log_respond.exception("Response generation FAILED: %s", exc)
        return (
            f"I encountered an error generating the response: {exc}. "
            "Please check the backend logs for details."
        )


# ── Main Pipeline ──────────────────────────────────────────────────────────────

async def chat(req: ChatRequest) -> AsyncGenerator[ThinkingStep | ChatResponseV2, None]:
    """
    FinBot pipeline entrypoint. Yields ThinkingStep objects in real-time as they
    are produced, then yields a ChatResponseV2 at the end.

    For backward compatibility, callers can also iterate and collect the final
    yielded ChatResponseV2 (e.g. chat_legacy).
    """
    log_pipe.info("=== Pipeline START ===")
    log_pipe.debug("Request: mode=%s history_len=%d", req.mode, len(req.history))

    step_num = 1

    # ── 1. Extract user message from history ─────────────────────────────────
    user_message = ""
    conversation_history: list[dict] = []
    for msg in req.history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        conversation_history.append({"role": role, "content": content})
        if role == "user" and content:
            user_message = content

    if not user_message:
        user_message = conversation_history[-1].get("content", "") if conversation_history else ""

    log_pipe.info("User message: %s", user_message[:200])

    # ── 2. Intent Routing ────────────────────────────────────────────────────
    yield _make_step(
        step_num=step_num,
        phase="intent_routing",
        status="active",
        content="Analysing user intent...",
    )
    step_num += 1

    route = route_intent(user_message)
    mode = route["mode"]

    routing_content = (
        f"Intent classified as [{mode.upper()}]. "
        f"Stock: '{route['stock_name']}' | Sector: '{route['sector_name']}'. "
        f"Reasoning: {route['reasoning']}"
    )
    yield _make_step(
        step_num=step_num,
        phase="intent_routing",
        status="success",
        content=routing_content,
    )
    step_num += 1

    # ── 3. Tool Execution ────────────────────────────────────────────────────
    tool_data: Any = None
    dashboard_payload: Any = None
    tool_source = ""

    yield _make_step(
        step_num=step_num,
        phase="tool_selection",
        status="active",
        content="Selecting tools...",
    )
    step_num += 1

    if mode == "company_info":
        stock_name = route["stock_name"] or user_message
        from tools.manager import get_mapped_entity
        futunn_mapped = get_mapped_entity(stock_name, "futunn.com")
        tv_mapped = get_mapped_entity(stock_name, "tradingview.com")
        inferred = _infer_exchange(futunn_mapped)
        sel_content = (
            f"Selected mode: COMPANY INFO. "
            f"Looking up '{stock_name}' in mapping files... "
            f"Futunn code: '{futunn_mapped}' | TradingView code: '{tv_mapped}'. "
            f"Inferred exchange: {inferred.upper()} → will use "
            f"{'Futunn (HK stocks)' if inferred == 'futunn' else 'TradingView (US/Global stocks)'}."
            f" If primary fails, will try the other platform as fallback."
        )
        yield _make_step(
            step_num=step_num,
            phase="tool_selection",
            status="success",
            content=sel_content,
            tool_used="futunn_company_info" if inferred == "futunn" else "tradingview_info",
        )
        step_num += 1

        yield _make_step(
            step_num=step_num,
            phase="tool_execution",
            status="active",
            content=f"Running company info scraper chain for '{stock_name}'...",
            tool_used="company_info_chain",
        )
        step_num += 1

        raw_data, tool_source = await _run_company_info_chain(stock_name)
        if raw_data and tool_source != "none":
            if tool_source == "futunn":
                dashboard_payload = build_company_info_payload(raw_data)
            else:
                dashboard_payload = build_tradingview_company_info_payload(raw_data)
            tool_data = raw_data
            preview = _truncate_preview(raw_data, max_len=150)
            fetched_name = raw_data.get("company_name") or raw_data.get("name", "unknown")
            yield _make_step(
                step_num=step_num,
                phase="tool_execution",
                status="success",
                content=f"{tool_source.upper()} company info fetched successfully — {fetched_name}",
                tool_used=f"{tool_source}_company_info",
                tool_result_preview=preview,
            )
        else:
            dashboard_payload = None
            tool_data = {}
            yield _make_step(
                step_num=step_num,
                phase="tool_execution",
                status="failed",
                content=f"All company info scrapers failed for '{stock_name}'. No data available.",
                tool_used="company_info_chain",
            )
        step_num += 1

    elif mode == "sector_analysis":
        sel_content = (
            "Selected mode: SECTOR ANALYSIS. "
            "Will try: TradingView → Futunn → YFinance (fallback chain)"
        )
        yield _make_step(
            step_num=step_num,
            phase="tool_selection",
            status="success",
            content=sel_content,
            tool_used="tradingview_sectors",
        )
        step_num += 1

        yield _make_step(
            step_num=step_num,
            phase="tool_execution",
            status="active",
            content="Executing sector scraper fallback chain...",
        )
        step_num += 1

        raw_sectors, tool_source = await _run_sector_chain()
        if raw_sectors:
            dashboard_payload = build_sector_payload(raw_sectors, tool_source)
            tool_data = raw_sectors
            yield _make_step(
                step_num=step_num,
                phase="tool_execution",
                status="success",
                content=f"Sector data fetched from {tool_source.upper()} — {len(raw_sectors)} sectors retrieved",
                tool_result_preview=_truncate_preview(raw_sectors[:3], max_len=200),
            )
        else:
            tool_data = []
            yield _make_step(
                step_num=step_num,
                phase="tool_execution",
                status="failed",
                content="All sector scrapers failed (TradingView, Futunn, YFinance). No data available.",
            )
        step_num += 1

    elif mode == "stock_analysis":
        stock_name = route["stock_name"] or user_message
        from tools.manager import get_mapped_entity
        futunn_mapped = get_mapped_entity(stock_name, "futunn.com")
        tv_mapped = get_mapped_entity(stock_name, "tradingview.com")
        ticker = futunn_mapped.strip() if futunn_mapped and futunn_mapped != stock_name else stock_name.strip()
        sel_content = (
            f"Selected mode: STOCK ANALYSIS. "
            f"Analysing '{stock_name}' (mapped ticker: '{ticker}'). "
            f"Pipeline: News Scraper → LLM Labeler → Sentiment Analyzer → "
            f"Ontology Engine → Daily Aggregator → Price Fetcher → Ensemble Model. "
            f"Futunn code: '{futunn_mapped}' | TradingView code: '{tv_mapped}'."
        )
        yield _make_step(
            step_num=step_num,
            phase="tool_selection",
            status="success",
            content=sel_content,
            tool_used="stock_analysis_pipeline",
        )
        step_num += 1

        # Yield pipeline steps as they arrive in real-time
        raw_result = {}
        tool_source = "none"
        # Valid ThinkingStep phase values that match internal pipeline step names
        _PIPELINE_PHASES = frozenset({
            "news_scraping", "llm_labeling", "sentiment",
            "ontology", "daily_agg", "price_fetch", "model",
        })
        async for event in _run_stock_analysis_chain(stock_name):
            if event[0] == "result":
                raw_result, tool_source = event[1]
            else:
                ps = event[1]  # step dict: {"step": "...", "status": "...", "message": "..."}
                step_name = ps["step"]
                # Skip the terminal "done" step — it is not a ThinkingStep phase
                if step_name == "done":
                    continue
                raw_status = ps["status"]
                if raw_status == "start":
                    mapped_status = "active"
                elif raw_status == "complete":
                    mapped_status = "success"
                else:
                    mapped_status = raw_status

                # Map pipeline phase names to the ThinkingStep literal phases.
                # Pipeline phases (news_scraping, llm_labeling, etc.) are valid.
                # Anything else (e.g., unexpected internal names) is remapped to tool_execution
                # to avoid Pydantic ValidationError.
                mapped_phase = step_name if step_name in _PIPELINE_PHASES else "tool_execution"

                yield _make_step(
                    step_num=step_num,
                    phase=mapped_phase,
                    status=mapped_status,
                    content=ps.get("message", ""),
                    tool_used=step_name,
                    tool_result_preview=ps.get("message") if mapped_status in ("success", "failed") else None,
                )
                step_num += 1

        if raw_result and tool_source == "stock_analysis":
            dashboard_payload = build_stock_analysis_payload(raw_result)
            tool_data = raw_result
            mp = raw_result.get("model_prediction", {})
            signal = mp.get("signal", "?")
            prob = mp.get("probability_up", 0.0)
            yield _make_step(
                step_num=step_num,
                phase="tool_execution",
                status="success",
                content=f"Stock analysis complete — {signal} signal (probability_up={prob:.4f})",
                tool_used="ensemble_model",
                tool_result_preview=f"{{\"signal\": \"{signal}\", \"probability_up\": {prob:.4f}}}",
            )
        else:
            dashboard_payload = None
            tool_data = {}
            yield _make_step(
                step_num=step_num,
                phase="tool_execution",
                status="failed",
                content=f"Stock analysis pipeline failed for '{stock_name}'. No data available.",
                tool_used="stock_analysis_pipeline",
            )
        step_num += 1

    else:
        yield _make_step(
            step_num=step_num,
            phase="tool_selection",
            status="skipped",
            content="No tool needed for this query — plain conversation mode",
        )
        step_num += 1

        yield _make_step(
            step_num=step_num,
            phase="tool_execution",
            status="skipped",
            content="Skipped — no tools requested",
        )
        step_num += 1

    # ── 4. Response Generation ───────────────────────────────────────────────
    yield _make_step(
        step_num=step_num,
        phase="response_generation",
        status="active",
        content="Generating investment analysis response...",
    )
    step_num += 1

    reply_text = generate_response(
        mode=mode,
        user_message=user_message,
        tool_data=tool_data,
        tool_source=tool_source,
        conversation_history=conversation_history,
    )

    yield _make_step(
        step_num=step_num,
        phase="response_generation",
        status="success",
        content="Response generated successfully",
    )

    log_pipe.info("=== Pipeline END — mode=%s steps=%d ===", mode, step_num - 1)

    yield ChatResponseV2(
        reply_text=reply_text,
        dashboard_payload=dashboard_payload,
        thinking_steps=[],  # steps are streamed separately; final payload has empty list
        mode_used=mode,  # type: ignore[arg-type]
    )


# ── Legacy wrapper (keeps existing /api/chat endpoint working) ─────────────────

async def chat_legacy(req: ChatRequest) -> ChatResponse:
    """
    Legacy wrapper. Consumes the async chat() generator to collect all steps,
    then returns the old ChatResponse shape.
    """
    steps: list[ThinkingStep] = []
    final_result: ChatResponseV2 | None = None

    async for item in chat(req):
        if isinstance(item, ChatResponseV2):
            final_result = item
        else:
            steps.append(item)

    if final_result is None:
        return ChatResponse(reply_text="", dashboard_payload=None)

    # Patch the final result with collected steps
    final_result.thinking_steps = steps

    return ChatResponse(
        reply_text=final_result.reply_text,
        dashboard_payload=final_result.dashboard_payload,
    )


