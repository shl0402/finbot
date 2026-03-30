# backend/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chat_service import chat
from models import ChatRequest, ChatResponse

app = FastAPI(
    title="FinChat API",
    description="Backend API for the FinChat financial chatbot",
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────

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

# ── Routes ─────────────────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(req: ChatRequest) -> ChatResponse:
    return chat(req)

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "finchat-backend"}