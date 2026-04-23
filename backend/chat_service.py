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

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
import json
import logging
from typing import Any, Optional

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
    resp = requests.post(
        GEMINI_API_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=60,
    )

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
        if mode not in ("company_info", "sector_analysis", "none"):
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


def _run_company_info_chain(stock_name: str) -> tuple[dict, str]:
    """
    Company info scraper chain with exchange-aware routing.

    Flow:
      1. Map stock_name to both Futunn and TradingView codes via mapping files.
      2. Infer which exchange the company belongs to from the Futunn mapping.
         - HK stocks → use Futunn
         - US/Global stocks → use TradingView
      3. If primary scraper fails, fall back to the other platform.

    Returns (result, source_tag) where source_tag is "futunn" or "tradingview".
    """
    from tools.manager import run_scraper_manager, get_mapped_entity

    log_tools.info("Company info chain for: %s", stock_name)

    # Step 1: Get mapped values for both platforms
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
        result = _try_company_scraper(stock_name, scraper_mode)
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


def _run_sector_chain() -> tuple[list, str]:
    """
    Try sector scrapers in order: TradingView -> Futunn -> YFinance.
    Returns (result_list, source_tag).
    """
    try:
        from tools.manager import run_scraper_manager

        log_tools.info("Trying TradingView sector scraper...")
        result = run_scraper_manager("dummy", "tradingview_sectors")
        if result and isinstance(result, list) and len(result) > 0:
            log_tools.info("TradingView sectors SUCCESS — %d sectors", len(result))
            return result, "tradingview"
        log_tools.warning("TradingView returned empty — trying Futunn next")

        log_tools.info("Trying Futunn sector scraper...")
        result = run_scraper_manager("dummy", "futunn_sectors")
        if result and isinstance(result, list) and len(result) > 0:
            log_tools.info("Futunn sectors SUCCESS — %d sectors", len(result))
            return result, "futunn"
        log_tools.warning("Futunn returned empty — trying YFinance next")

        log_tools.info("Trying YFinance sector scraper...")
        result = run_scraper_manager("dummy", "yfinance_sectors")
        if result and isinstance(result, list) and len(result) > 0:
            log_tools.info("YFinance sectors SUCCESS — %d sectors", len(result))
            return result, "yfinance"
        log_tools.error("All sector scrapers failed")

    except Exception as exc:
        log_tools.exception("Sector chain FAILED: %s", exc)

    return [], "none"


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

def chat(req: ChatRequest):
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

        raw_data, tool_source = _run_company_info_chain(stock_name)
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

        raw_sectors, tool_source = _run_sector_chain()
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

def chat_legacy(req: ChatRequest) -> ChatResponse:
    """
    Legacy wrapper. Consumes the chat() generator to collect all steps,
    then returns the old ChatResponse shape.
    """
    steps: list[ThinkingStep] = []
    final_result: ChatResponseV2 | None = None

    for item in chat(req):
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


# ── Legacy wrapper (keeps existing /api/chat endpoint working) ─────────────────

def chat_legacy(req: ChatRequest) -> ChatResponse:
    """
    Legacy wrapper. Runs the pipeline but returns the old ChatResponse shape.
    Used by the existing POST /api/chat endpoint.
    """
    v2 = chat(req)
    return ChatResponse(
        reply_text=v2.reply_text,
        dashboard_payload=v2.dashboard_payload,
    )
