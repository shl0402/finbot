# FinChat

A financial chatbot application with a Next.js frontend and FastAPI backend, powered by local LLM models via [Ollama](https://ollama.com/).

## Project Structure

```
finbot/
├── backend/          FastAPI API server (chat, dashboard data)
├── frontend/         Next.js web UI (React 19 + Tailwind CSS v4)
├── FinBot/           Streamlit prototype (legacy)
└── README.md
```

## Architecture

- **Frontend** — Next.js 16 app router, dark-themed UI, real-time streaming, branched chat history (tree-based state), inline data dashboards.
- **Backend** — FastAPI, Ollama integration for LLM inference (text + vision), Pydantic request/response models.
- **Communication** — Frontend proxies to backend via `POST /api/chat`; CORS is open for local dev (`localhost:3000`, `localhost:5173/5174`).

## Prerequisites

- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com/) running locally
- Ollama models pulled:
  - `mistral-small3.1:24b-instruct-2503-q4_K_M` (default text model)
  - `llava` (or your `OLLAMA_VISION_MODEL`) for image understanding

## Setup

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Swagger docs are at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` in your browser.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_VISION_MODEL` | `llava` | Ollama model used for image inputs |

## Chat Modes

| Mode | Trigger | Dashboard |
|---|---|---|
| `none` | Default | None |
| `market_discovery` | Keywords: market, discovery, setup, picks, recommend, best stock | Stock metrics cards + risk/reward scores |
| `stock_deep_analysis` | Keywords: chart, technical, candlestick, price, NVDA, stock deep | Candlestick chart + technical stats + sentiment analysis |

## API Reference

### `POST /api/chat`

**Request body** — `ChatRequest`

```json
{
  "history": [
    { "role": "user", "content": "What is NVDA trading at?" },
    { "role": "assistant", "content": "NVDA is currently around $880." }
  ],
  "mode": "stock_deep_analysis"
}
```

**Response** — `ChatResponse`

```json
{
  "reply_text": "NVDA is trading at approximately $880...",
  "dashboard_payload": {
    "type": "chart",
    "symbol": "NVDA",
    "chart_data": [ ... ],
    "sentiment_score": 0.75
  }
}
```

### `GET /api/health`

Returns `{ "status": "ok", "service": "finchat-backend" }`.
