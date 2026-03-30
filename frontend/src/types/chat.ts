// frontend/src/types/chat.ts

export type MessageRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  /** Data URLs from image upload (shown in UI; base64 sent to API separately). */
  images?: string[];
  timestamp: Date;
  parentId: string | null;
  children: string[]; // child message IDs (each child = one "version" of this branch)
  dashboardPayload?: DashboardPayload;
}

// ── Dashboard payload types ──────────────────────────────────────

export interface MetricCard {
  label: string;
  value: string;
  delta?: string;
  deltaColor?: "normal" | "inverse";
}

export interface MarketDiscoveryPayload {
  type: "metrics";
  symbol: string;
  name: string;
  metrics: MetricCard[];
  rrScore?: { ratio: string; description: string };
}

export interface SentimentWord {
  word: string;
  score: number;
  size: number;
}

export interface SentimentBarItem {
  word: string;
  count: number;
}

export interface ChartPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface ChartPayload {
  type: "chart";
  symbol: string;
  name: string;
  chartData: ChartPoint[];
  keyStats?: MetricCard[];
  sentimentScore?: number;
  sentimentLabel?: string;
  wordCloud?: SentimentWord[];
  topPositive?: SentimentBarItem[];
  topNegative?: SentimentBarItem[];
  newsCount?: number;
}

export interface CodePayload {
  type: "code";
  language: string;
  code: string;
  description: string;
}

export type DashboardPayload =
  | MarketDiscoveryPayload
  | ChartPayload
  | CodePayload
  | null;

// ── API types ───────────────────────────────────────────────────

export type ChatMode = "none" | "market_discovery" | "stock_deep_analysis";

/** One turn for POST /api/chat (optional images = raw base64 or data URLs; backend strips prefix). */
export interface ChatHistoryItem {
  role: MessageRole;
  content: string;
  images?: string[];
}

export interface ChatRequest {
  history: ChatHistoryItem[];
  mode: ChatMode;
}

export interface ChatResponse {
  reply_text: string;
  dashboard_payload: DashboardPayload;
}
