# backend/main.py

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import logging
import json
import asyncio

from chat_service import chat, chat_legacy
from logging_config import setup_logging
from models import ChatRequest, ChatResponse

# ── Bootstrap ──────────────────────────────────────────────────────────────────

setup_logging()
logger = logging.getLogger("finbot.main")

app = FastAPI(
    title="FinChat API",
    description="Financial chatbot backend — Gemini-powered with tool integration",
    version="2.0.0",
)

# ── CORS ───────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── SSE Helper ────────────────────────────────────────────────────────────────

def sse_event(data: dict, event: str = "message") -> bytes:
    """Serialize a dict as an SSE data line."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")


async def event_stream(coro):
    """
    Run a coroutine that yields (step_or_response) objects
    and stream each one as an SSE event.
    """
    try:
        async for item in coro:
            yield sse_event({"type": "step", "data": item})
    except Exception as exc:
        logger.exception("SSE stream error: %s", exc)
        yield sse_event({"type": "error", "data": str(exc)}, event="error")
    finally:
        yield sse_event({"type": "done"}, event="done")


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(req: ChatRequest) -> ChatResponse:
    """
    Legacy synchronous chat endpoint.
    Uses chat_legacy() which runs the pipeline but returns ChatResponseV2
    cast to the old ChatResponse shape.
    """
    logger.info("POST /api/chat — mode=%s history_len=%d", req.mode, len(req.history))
    try:
        return chat_legacy(req)
    except Exception as exc:
        logger.exception("chat endpoint error: %s", exc)
        return ChatResponse(
            reply_text=f"Internal server error: {exc}",
            dashboard_payload=None,
        )


@app.post("/api/chat/stream")
async def api_chat_stream(req: Request):
    """
    SSE streaming endpoint for real-time thinking process display.
    Streams each ThinkingStep as it is produced, then streams the final response.
    """
    logger.info("POST /api/chat/stream")

    try:
        body = await req.json()
    except Exception as exc:
        logger.warning("Invalid JSON in /api/chat/stream: %s", exc)
        return StreamingResponse(
            event_stream(
                asyncio.sleep(0),
            ),
            media_type="text/event-stream",
        )

    chat_req = ChatRequest(**body)
    logger.info("/api/chat/stream — history_len=%d", len(chat_req.history))

    return StreamingResponse(
        _stream_pipeline(chat_req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _stream_pipeline(req: ChatRequest):
    """
    Async generator that runs the chat() generator and yields SSE events for each step
    in real-time as it is produced, then streams the final response.
    """
    from chat_service import chat
    from models import ThinkingStep, ChatResponseV2

    sentinel = object()

    def run_sync():
        return chat(req)

    def next_item(gen):
        """next() that swallows StopIteration and returns sentinel instead."""
        try:
            return next(gen)
        except StopIteration:
            return sentinel

    loop = asyncio.get_running_loop()
    sync_gen = await loop.run_in_executor(None, run_sync)

    steps: list[ThinkingStep] = []
    final_result: ChatResponseV2 | None = None

    while True:
        item = await loop.run_in_executor(None, next_item, sync_gen)
        if item is sentinel:
            break

        if isinstance(item, ChatResponseV2):
            final_result = item
        else:
            step = item  # ThinkingStep
            steps.append(step)
            yield sse_event({"type": "step", "data": step.model_dump()})

    if final_result is None:
        final_result = ChatResponseV2(reply_text="", thinking_steps=[], mode_used="none")

    # Patch final result with streamed steps for completeness
    final_result.thinking_steps = steps

    yield sse_event({
        "type": "response",
        "data": {
            "reply_text": final_result.reply_text,
            "dashboard_payload": (
                final_result.dashboard_payload.model_dump()
                if final_result.dashboard_payload is not None
                else None
            ),
            "thinking_steps": [s.model_dump() for s in steps],
            "mode_used": final_result.mode_used,
        }
    })


@app.post("/api/log")
async def api_log(req: Request):
    """
    Receive error logs from the frontend and log them server-side.
    """
    try:
        body = await req.json()
        level = body.get("level", "info")
        message = body.get("message", "")
        stack = body.get("stack", "")
        url = body.get("url", "")
        ua = body.get("userAgent", "")

        log_msg = f"[FE] {message}"
        if url:
            log_msg += f" | URL: {url}"
        if ua:
            log_msg += f" | UA: {ua}"
        if stack:
            log_msg += f"\n{stack}"

        if level == "error":
            logger.error(log_msg)
        elif level == "warn":
            logger.warning(log_msg)
        elif level == "debug":
            logger.debug(log_msg)
        else:
            logger.info(log_msg)

    except Exception as exc:
        logger.warning("Failed to process frontend log: %s", exc)

    return {"status": "ok"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "finchat-backend", "version": "2.0.0"}
