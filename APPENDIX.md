# FinChat — Technical Appendix

This document supplements the main [README.md](./README.md). It covers deployment commands, API reference, scraper tool parameters, LLM prompts, and a deep-dive into the system architecture.

---

## A. Deploy Commands

### Backend

```bash
# 1. Clone / navigate to project
cd /path/to/finbot/backend

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
# Create backend/.env with GEMINI_API_KEY=your_key_here
cp .env.example .env            # if an example file exists
nano .env                       # edit with your API key

# 5. Development (with hot-reload)
uvicorn main:app --reload --port 8000

# 6. Production
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

The backend will be available at `http://localhost:8000`. Swagger docs: `http://localhost:8000/docs`.

**Required environment variables** (create `backend/.env`):

```env
GEMINI_API_KEY=your_google_gemini_api_key_here
```

### Frontend

```bash
# 1. Navigate to frontend
cd /path/to/finbot/frontend

# 2. Install dependencies
npm install

# 3. Development
npm run dev

# 4. Production build
npm run build
npm start
```

The frontend will be available at `http://localhost:3000`.

### Initial Setup (First Run)

```bash
# Install Playwright browsers (required for web scrapers)
cd backend
playwright install chromium

# Verify Python dependencies
python -c "import fastapi, pydantic, requests, yfinance; print('OK')"
```

---

## B. API Reference

### `POST /api/chat`

Legacy synchronous endpoint. Returns the full response after the pipeline completes.

**Request body — `ChatRequest`:**

```json
{
  "history": [
    { "role": "user", "content": "Tell me about Xiaomi" },
    { "role": "assistant", "content": "Xiaomi is a Chinese electronics company..." }
  ],
  "mode": "none"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `history` | `array` | Yes | List of chat messages. Each message has `role` ("user" or "assistant") and `content` (string). `images` (array of base64 strings) is optional on user messages. |
| `mode` | `string` | No | Hint for routing. One of: `"none"`, `"market_discovery"`, `"stock_deep_analysis"`. Defaults to `"none"`; the Gemini router will override this. |

**Response — `ChatResponse`:**

```json
{
  "reply_text": "Based on the data retrieved...",
  "dashboard_payload": {
    "type": "company_info",
    "companyName": "Xiaomi Corporation",
    "symbol": "1810",
    "price": "27.45 HKD",
    "change": "+0.85",
    "changePercent": "+3.19%",
    "marketCap": "549.34B HKD",
    "peRatio": "18.2",
    "description": "Xiaomi Corporation is a Chinese...",
    "stats": [
      { "label": "Market Cap", "value": "549.34B HKD" },
      { "label": "P/E (TTM)", "value": "18.2" }
    ],
    "profile": {
      "CEO": "Lei Jun",
      "Headquarters": "Beijing, China"
    }
  }
}
```

Possible `dashboard_payload` types: `company_info`, `sector`, `stock_analysis`, `metrics`, `chart`, `code`, or `null`.

---

### `POST /api/chat/stream`

SSE streaming endpoint. Streams each thinking step as it is produced, then the final response. Recommended for production use.

**Request body:** Same as `POST /api/chat`.

**Response:** `text/event-stream` (SSE). Each event has a `type` field.

**SSE event types:**

| Event `type` | Description | Payload |
|---|---|---|
| `step` | A thinking step was produced by the pipeline | `{ "type": "step", "data": ThinkingStep }` |
| `response` | Final response (all steps + reply + dashboard) | `{ "type": "response", "data": ChatResponseV2 }` |
| `error` | An error occurred during streaming | `{ "type": "error", "data": "<error message>" }` |
| `done` | Stream completed | `{ "type": "done" }` |

**`ThinkingStep` object (emitted in `step` events):**

```json
{
  "stepNumber": 1,
  "phase": "intent_routing",
  "status": "success",
  "content": "Gemini classified query as company_info for 'Xiaomi'",
  "toolUsed": "Gemini 2.5-flash-lite",
  "toolResultPreview": null
}
```

Possible phases: `intent_routing`, `tool_selection`, `tool_execution`, `response_generation`, `news_scraping`, `llm_labeling`, `sentiment`, `ontology`, `daily_agg`, `price_fetch`, `model`

Possible statuses: `active`, `success`, `failed`, `skipped`

**Final `response` event payload:**

```json
{
  "type": "response",
  "data": {
    "replyText": "Based on the data retrieved...",
    "dashboardPayload": { ... },
    "thinkingSteps": [ /* array of ThinkingStep objects */ ],
    "modeUsed": "company_info"
  }
}
```

---

### `GET /api/health`

Health check endpoint.

**Response:**

```json
{
  "status": "ok",
  "service": "finchat-backend",
  "version": "2.0.0"
}
```

---

### `POST /api/log`

Receives error logs from the frontend for server-side logging.

**Request body:**

```json
{
  "level": "error",
  "message": "Uncaught TypeError in ChatInterface",
  "stack": "TypeError: undefined is not an object...",
  "url": "http://localhost:3000/",
  "userAgent": "Mozilla/5.0..."
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `level` | `string` | No | Log level: `"debug"`, `"info"`, `"warn"`, `"error"`. Defaults to `"info"`. |
| `message` | `string` | Yes | Log message text. |
| `stack` | `string` | No | JavaScript error stack trace. |
| `url` | `string` | No | Browser URL where the error occurred. |
| `userAgent` | `string` | No | Browser user agent string. |

**Response:** `{ "status": "ok" }`

---

## C. Tool Function Parameters

All scraper tools are invoked via `tools/manager.py`'s `run_scraper_manager(stock_name, mode, **kwargs)` function. It is called from `chat_service.py` within the tool execution chains.

### Mode Reference

| Mode | Description | Input | Notes |
|---|---|---|---|
| `futunn_info` | Company info via Futunn | `stock_name` | Primary for HK stocks. Returns company name, price, change, stats, profile. |
| `tradingview_info` | Company info via TradingView | `stock_name` | Primary for US/Global stocks. Returns extended key stats, about section, analyst ratings. |
| `tradingview_sectors` | Sector heatmap via TradingView | `dummy` (ignored) | Returns all sectors with change %, market cap, dividend yield, volume, performance timeframes. Sets `interactive=True`. |
| `futunn_sectors` | Sector heatmap via Futunn | `dummy` (ignored) | Returns sectors with change %. Fallback when TradingView fails. |
| `yfinance_sectors` | Sector heatmap via YFinance | `dummy` (ignored) | Returns sectors with change %. Last resort fallback. |
| `futunn_news` | Recent news via Futunn | `stock_name` | Returns title, time, source, link, short description. |
| `futunn_news_days` | News within date range | `stock_name`, `num_days`, `max_per_day` | Used by stock analysis pipeline (20 days, max 2/day). |
| `tradingview_news` | News via TradingView | `stock_name` | Returns similar fields to Futunn news. |
| `futunn_company_analysis` | Technical analysis via Futunn | `stock_name` | Returns technical indicators. |

### Fallback Chains

- **Company info:** `futunn_info` → `tradingview_info`
- **Sector analysis:** `tradingview_sectors` → `futunn_sectors` → `yfinance_sectors`
- **News:** `futunn_news_days` (primary, used in stock analysis)

---

## D. LLM Prompts

All prompts are defined in `backend/prompts.yaml` and loaded at server startup. Restart the server after editing this file.

### D.1 Intent Routing Prompts

**System instruction (`routing.system`):**

```
You are a precise financial analysis intent router. Always respond with valid JSON only.
No markdown fences, no extra text.
```

**Routing prompt (`routing.prompt`):**

```
You are a financial analysis intent router. Your job is to classify a user query and
extract key entities.

Respond ONLY with valid JSON (no markdown, no explanation). The JSON must have these
exact keys:
{
  "mode": "company_info" | "sector_analysis" | "stock_analysis" | "none",
  "stock_name": "the stock/company name mentioned, or empty string",
  "sector_name": "the sector name mentioned, or empty string",
  "reasoning": "one sentence explaining why you chose this mode"
}

Rules:
- "company_info": user asks about a specific company's profile, financials, stock price,
  or description. Look for a stock name or company name.
- "sector_analysis": user asks about sectors, industries, market heatmaps, sector
  performance, or which sector to invest in.
- "stock_analysis": user asks whether a stock is worth buying/selling, wants a
  prediction, asks about sentiment, wants to "analyze" a stock, asks "should I invest
  in X", or asks about a stock's outlook. This triggers the full ML pipeline with news,
  sentiment, and model prediction.
- "none": general conversation, greetings, or questions that don't need tools.

Examples:
- "Tell me about Xiaomi" -> {"mode":"company_info","stock_name":"xiaomi","sector_name":"","reasoning":"..."}
- "Which sector is best to invest in Hong Kong right now?" -> {"mode":"sector_analysis",...}
- "What is the AI sector performance today?" -> {"mode":"sector_analysis","sector_name":"AI",...}
- "Should I buy Xiaomi?" -> {"mode":"stock_analysis","stock_name":"xiaomi",...}
- "Is BYD a good buy right now?" -> {"mode":"stock_analysis","stock_name":"byd",...}
- "How are you doing?" -> {"mode":"none",...}
```

### D.2 Response Generation Prompts

**System instruction (`system_response`):**

```
You are FinBot, a professional Hong Kong / global financial analysis assistant.

Rules:
- Answer the user's specific question FIRST and directly. Do NOT dump all available data.
- Only mention additional data points if they meaningfully support or contextualise the answer.
- Keep responses concise — 2-4 sentences for a specific question, or a short paragraph for a broader one.
- Use bullet points for data only when comparing multiple items (e.g. sector rankings).
- If you don't have enough data to answer, say so honestly.
- Do NOT make up numbers or statistics. Only use data provided in the context.
- The dashboard panel already shows full details — do not repeat data the user can see there.
```

**Company info response template (`response_templates.company_info`):**

```
You are answering a user question about a company. The dashboard beside this response
shows the full company profile, financials, and key statistics.

User's question: {user_message}

Retrieved company data:
{tool_data}

Instructions:
- Answer the user's question directly and concisely (2-4 sentences).
- If the user asked a specific metric (e.g. PE ratio, market cap), give that number with a brief interpretation.
- If the user asked a broad question (e.g. "tell me about BYD"), give a brief 2-3 sentence overview.
- Reference the dashboard for full details — do not reproduce everything here.
```

**Sector analysis response template (`response_templates.sector_analysis`):**

```
You are answering a user question about sector/industry performance. The dashboard beside
this response shows the full sector heatmap.

User's question: {user_message}

Retrieved sector data:
{tool_data}

Instructions:
- Answer the user's question directly.
- If the user asked about a specific sector (e.g. "how is tech doing?"), focus on that sector and its relevant peers.
- If the user asked a broad question (e.g. "which sectors are hot today?"), give top/bottom 2-3 sectors with brief reasons.
- Reference the dashboard for the full heatmap — do not list every sector.
```

**Stock analysis response template (`response_templates.stock_analysis`):**

```
You are answering a user question about a stock's investment outlook. The dashboard beside
this response shows the full analysis.

User's question: {user_message}

Retrieved analysis data:
{tool_data}

Instructions:
- Extract the signal and probability_up value from the tool_data JSON:
    * signal: either "BUY" or "SELL" (from model_prediction.signal)
    * probability_up: a float between 0 and 1 (from model_prediction.probability_up)
    * price_summary: recent price data (from price_summary)
- ALWAYS report the model's signal and probability clearly, e.g. "The model predicts a
  BUY signal with 54.65% probability of upside."
- If the user asked about SHORTING:
    * A BUY signal (upside) means the stock is expected to go UP — shorting is risky.
    * A SELL signal (downside) means the stock is expected to go DOWN — shorting aligns with the trend.
- Use the model's prediction as the authoritative answer — do NOT derive your own BUY/SELL from raw news or sentiment scores.
- Briefly explain the key factors the model used (e.g., recent sentiment trend, notable headlines, price momentum).
- Reference the dashboard for full news details and technical indicators.
- Keep the response concise — the dashboard handles the depth.
```

**No-tool response template (`response_templates.none`):**

```
The conversation history is below. Answer the user's question naturally as FinBot.

User question: {user_message}
```

---

## E. Architecture Deep Dive

### E.1 Frontend Architecture

**Framework:** Next.js 16 App Router, React 19, TypeScript, Tailwind CSS v4.

**Key files:**

| File | Role |
|---|---|
| `src/components/ChatInterface.tsx` | Main chat UI. Manages message tree state, SSE connection, streaming display. |
| `src/components/ChatMessageItem.tsx` | Renders a single message bubble with optional dashboard. |
| `src/components/PromptInput.tsx` | Text + image input with drag-and-drop. |
| `src/components/ThinkingProcess.tsx` | Real-time thinking steps display during pipeline execution. |
| `src/components/CompanyDashboard.tsx` | Company info dashboard with stats grid and profile section. |
| `src/components/SectorDashboard.tsx` | Sector heatmap with hover tooltips, click-to-flip bar charts, and market-cap pie chart. |
| `src/components/StockAnalysisDashboard.tsx` | Full ML analysis dashboard with candlestick chart, news feed, sentiment timeline. |
| `src/lib/api.ts` | API client. `POST /api/chat` (legacy) and `EventSource` for SSE streaming. |
| `src/types/chat.ts` | TypeScript interfaces matching all backend Pydantic models. |

**Chat history:** Tree-based state. Each message has a `parentId` and a `children` array, enabling branched conversation history.

**SSE streaming:** The frontend opens an `EventSource`-equivalent via `fetch` with `ReadableStream` to consume SSE events. Each `step` event updates the `ThinkingProcess` component in real-time. The final `response` event triggers rendering of the dashboard.

**SectorDashboard interactivity:**
- **Hover:** Shows a rich tooltip portal (rendered via React portal to escape overflow clipping) with full sector details, extended stats, and performance across timeframes.
- **Click:** Flips the selected card into a larger panel (~3x size) showing a grouped bar chart (recharts `BarChart`) of performance across all available timeframes. A purple border highlights the active card. "Back" button or re-clicking closes it.
- **Pie chart:** Below the heatmap, a donut chart (recharts `PieChart`) shows market-cap distribution for the top 8 sectors. Legend uses mini progress bars for space efficiency. Only renders when market cap data is available (TradingView source).

**Charts:**
- Candlestick/OHLCV chart: `lightweight-charts` (TradingView's open-source library)
- Bar/pie charts: `recharts`

---

### E.2 Backend Architecture

**Framework:** FastAPI + Uvicorn, async throughout via Python `asyncio`.

**Key files:**

| File | Role |
|---|---|
| `main.py` | FastAPI app, CORS config, SSE streaming helper, route definitions |
| `chat_service.py` | 3-stage pipeline: intent routing, tool execution, response generation |
| `dashboard_gen.py` | Payload builders: `build_company_info_payload`, `build_sector_payload`, `build_stock_analysis_payload` |
| `models.py` | Pydantic v2 schemas for all request/response models |
| `prompts.yaml` | All LLM prompts, loaded at startup |
| `logging_config.py` | Structured logging setup with named loggers (`finbot.router`, `finbot.tools`, etc.) |
| `tools/manager.py` | Scraper router with exchange-aware routing and fallback chains |
| `tools/stock_analysis.py` | Full ML pipeline: news → LLM labeler → sentiment → ontology → aggregation → price → model |

---

### E.3 Gemini API Integration

**Model:** `gemini-2.5-flash-lite` (v1beta endpoint)

**URL pattern:**
```
https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={GEMINI_API_KEY}
```

**Retry policy (added to `_gen_content`):**
- Up to **3 attempts** per request
- Network errors and **5xx server errors** trigger retry with **exponential backoff** (1.5s, 2.25s)
- **4xx client errors** (bad request, auth failure) fail immediately — no retry

**Used in two places:**
1. **Intent routing** — single-shot JSON classification, temperature=0.1
2. **Response generation** — natural language reply using tool context, temperature=0.3

---

### E.4 Scraper Architecture

All scrapers are invoked via `tools/manager.py`. There are three data source families:

**Futunn (`futunn_*.py`):**
- HK-stock focused. Used as primary for HK-listed companies.
- Scraper modes: `futunn_info`, `futunn_sectors`, `futunn_news`, `futunn_news_days`, `futunn_company_analysis`
- Technology: `requests` + `BeautifulSoup` for HTML parsing, `playwright` for JS-rendered pages.

**TradingView (`tradingview_*.py`):**
- US/Global stocks and sector heatmaps.
- Scraper modes: `tradingview_info`, `tradingview_sectors`, `tradingview_news`
- Technology: `playwright` (headless Chromium) — required because TradingView is heavily JavaScript-rendered.

**YFinance (`yfinance_*.py`):**
- Python `yfinance` library for price data and sector heatmaps.
- Scraper modes: `yfinance_sectors`, `yfinance_price_history`
- Used as last-resort fallback for sector data.

**Exchange inference logic** (in `chat_service.py` `_infer_exchange`):
```
Futunn code ends in -HK  → Futunn (HK stocks)
Futunn code ends in -US/-UK/-EU/-DE/-FR/-JP/-AU  → TradingView
Code prefixed with NASDAQ/NYSE/AMEX/LSE/TSX/ASX  → TradingView
Everything else  → Futunn (default)
```

---

### E.5 ML Pipeline (Stock Analysis)

The full ML pipeline runs in `tools/stock_analysis.py` via `run_prediction()`. It is an async generator that yields step events as each phase completes.

**Pipeline stages:**

```
┌─────────────────────────────────────────────────────────┐
│  1. News Scraping (Futunn, 20 days, max 2/day)          │
│     → news_items: title, time, source, link, desc       │
└──────────────────────────┬──────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  2. LLM Labeling (Gemini 2.5-flash-lite)               │
│     → relation_id, fixed_sentiment_applicable,          │
│       related_company, chain_of_thought, confidence       │
└──────────────────────────┬──────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  3. Sentiment Scoring (FinBERT → TextBlob fallback)     │
│     → sentiment_label, raw_sentiment_score,             │
│       positive_prob, negative_prob, neutral_prob        │
└──────────────────────────┬──────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  4. Ontology Adjustment                                 │
│     Competitor mentioned → invert sentiment              │
│     Supplier/Index/Match → pass through unchanged        │
│     Entity map covers 80+ HK-listed stocks with         │
│     competitor/supplier/index relations                 │
└──────────────────────────┬──────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  5. Daily Aggregation (20-day lookback)                 │
│     → sentiment_mean, sentiment_lag_1/2/3,            │
│       news_count, news_lag_1/2/3                       │
└──────────────────────────┬──────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  6. Price Features (yfinance + TA indicators)          │
│     → close, Volume, returns, volatility_10d,          │
│       volume_change, price_range, RSI, MACD, vwap,     │
│       hsi_volatility                                   │
└──────────────────────────┬──────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  7. Ensemble Model (GBM + LSTM + Meta Stacking)        │
│     → BUY / SELL signal, probability_up (0.0–1.0)      │
└─────────────────────────────────────────────────────────┘
```

**Model components:**

| Model | Type | Purpose |
|---|---|---|
| GBM | Gradient Boosting (sklearn-style) | Captures non-linear feature interactions |
| LSTM | Long Short-Term Memory (Keras `.keras`) | Sequential pattern recognition on price + sentiment |
| Meta Stacker | Logistic Regression | Combines GBM + LSTM outputs into final probability |

**Entity ontology** (`tools/stock_analysis.py` `_ENTITY_MAP`):
- Maps 80+ HK stock tickers to their competitors, suppliers, and index memberships
- **Competitor** mentioned in a headline → sentiment is **inverted** (bad news for competitor = good for target)
- **Supplier/Partner/Index** mentioned → sentiment passes through unchanged
- Unknown entities → classified as `0.0` (no relation), not guessed

**Feature scalers:** Global price and sentiment scalers are serialised as `.pkl` files in `tools/models/` and loaded at prediction time to normalise input features.

---

### E.6 Data Flow Summary

```
User query
    │
    ▼
FastAPI /api/chat/stream  (SSE)
    │
    ▼
chat_service.chat()  [async generator]
    │
    ├─ Step 1: route_intent()     → Gemini routing  [ThinkingStep: intent_routing]
    │
    ├─ Step 2a: _run_company_info_chain()
    │             or _run_sector_chain()
    │             or _run_stock_analysis_chain()  [ThinkingStep: tool_execution]
    │                 │
    │                 ├─ manager.run_scraper_manager()
    │                 │   ├─ futunn_company_info_scrawler.py
    │                 │   ├─ tradingview_sector_change_scrawler.py
    │                 │   ├─ yfinance_live_numerical_data_scraper.py
    │                 │   └─ (with fallback chains)
    │                 │
    │                 └─ stock_analysis.run_prediction()
    │                       ├─ news scraping
    │                       ├─ LLM labeling (Gemini)
    │                       ├─ sentiment (FinBERT)
    │                       ├─ ontology adjustment
    │                       ├─ daily aggregation
    │                       ├─ price features (yfinance)
    │                       └─ ensemble model  [ThinkingStep: model]
    │
    ├─ Step 3: dashboard_gen.build_*_payload()  (transform raw data → typed payload)
    │
    └─ Step 4: _gen_content()  → Gemini response generation  [ThinkingStep: response_generation]

SSE events emitted:
    → step events  (ThinkingStep per phase)
    → response event  (reply_text + dashboard_payload + all steps)
    → done event
```

---

*FinChat Technical Appendix — generated from source code at commit.*
