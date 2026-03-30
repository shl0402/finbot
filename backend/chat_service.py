# backend/chat_service.py

import os

import ollama
from models import ChatRequest, ChatResponse, MarketDiscoveryPayload, ChartPayload, CodePayload
from dashboard_gen import generate

DashboardPayload = MarketDiscoveryPayload | ChartPayload | CodePayload | None

TEXT_MODEL = "mistral-small3.1:24b-instruct-2503-q4_K_M"
VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "llava")


def normalize_image_b64(s: str) -> str:
    """Strip data-URL prefix so Ollama receives raw base64."""
    s = (s or "").strip()
    if s.startswith("data:"):
        comma = s.find(",")
        if comma != -1:
            return s[comma + 1 :]
    return s


def build_ollama_messages(history: list[dict]) -> list[dict]:
    """
    Convert our flat history into Ollama message format.
    Supports both text-only and multi-image (vision) messages.
    """
    ollama_msgs = []
    for msg in history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        raw_images = msg.get("images") or []
        images = [normalize_image_b64(x) for x in raw_images if x]

        if images:
            ollama_msgs.append({
                "role": role,
                "content": content or "What do you see in this image?",
                "images": images,
            })
        else:
            ollama_msgs.append({
                "role": role,
                "content": content,
            })

    return ollama_msgs


def dashboard_type_from_mode(mode: str) -> str | None:
    if mode == "market_discovery":
        return "metrics"
    if mode == "stock_deep_analysis":
        return "chart"
    return None


def chat(req: ChatRequest) -> ChatResponse:
    # 1. Determine dashboard type from explicit mode selection (not keyword auto-detection)
    dashboard_type = dashboard_type_from_mode(req.mode)
    dashboard_payload: DashboardPayload = generate(dashboard_type)

    # 2. Build messages for Ollama
    ollama_messages = build_ollama_messages(req.history)
    has_images = any(bool(msg.get("images")) for msg in req.history)
    model = VISION_MODEL if has_images else TEXT_MODEL

    # 3. Call Ollama
    try:
        # Text: mistral-small3.1 (no vision). Images: llava (or OLLAMA_VISION_MODEL), pull if missing.
        response = ollama.chat(
            model=model,
            messages=ollama_messages,
            options={"temperature": 0.7},
        )
        reply_text = response["message"]["content"]
    except Exception as e:
        reply_text = (
            f"[Ollama Error] {str(e)}\n\n"
            "Tip: For images, ensure a vision model is installed, e.g. `ollama pull llava` "
            f"(using `{VISION_MODEL}` when images are sent). Text-only uses `{TEXT_MODEL}`."
        )

    return ChatResponse(
        reply_text=reply_text,
        dashboard_payload=dashboard_payload,
    )
