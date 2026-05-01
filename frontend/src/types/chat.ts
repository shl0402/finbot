// frontend/src/types/chat.ts

export type MessageRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  images?: string[];
  timestamp: Date;
  parentId: string | null;
  children: string[];
  dashboardPayload?: DashboardPayload;
  thinkingSteps?: ThinkingStep[]; // stored per-message
}

// ── Thinking Steps ─────────────────────────────────────────────────────────────

export type Phase =
  | "intent_routing"
  | "tool_selection"
  | "tool_execution"
  | "response_generation"
  | "news_scraping"
  | "llm_labeling"
  | "sentiment"
  | "ontology"
  | "daily_agg"
  | "price_fetch"
  | "model";

export type StepStatus = "active" | "success" | "failed" | "skipped";

export interface ThinkingStep {
  stepNumber: number;
  phase: Phase;
  status: StepStatus;
  content: string;
  toolUsed?: string;
  toolResultPreview?: string;
}

// ── Metric Cards ────────────────────────────────────────────────────────────────

export interface MetricCard {
  label: string;
  value: string;
  delta?: string;
  deltaColor?: "normal" | "inverse";
}

// ── Dashboard Payload Types ──────────────────────────────────────────────────────

export interface MarketDiscoveryPayload {
  type: "metrics";
  symbol: string;
  name: string;
  metrics: MetricCard[];
  rrScore?: { ratio: string; description: string };
}

export interface ChartPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
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

export interface CompanyInfoPayload {
  type: "company_info";
  companyName: string;
  symbol: string;
  price: string;
  change: string;
  changePercent: string;
  marketCap: string;
  peRatio: string;
  description: string;
  stats: MetricCard[];
  profile: Record<string, string>;
}

// Single sector item — optional fields only present for TradingView source
export interface SectorItem {
  sector: string;
  changePercent: string;
  link: string;
  marketCap?: string;
  dividendYield?: string;
  volume?: string;
  industriesCount?: string;
  stocksCount?: string;
  perf1w?: string;
  perf1m?: string;
  perf3m?: string;
  perf6m?: string;
  perfYtd?: string;
  perf1y?: string;
  perf5y?: string;
  perf10y?: string;
  perfAllTime?: string;
}

export interface SectorPayload {
  type: "sector";
  source: "tradingview" | "futunn" | "yfinance";
  interactive: boolean;
  sectors: SectorItem[];
}

export interface NewsItemPayload {
  title: string;
  time: string;
  source: string;
  link: string;
  shortDescription: string;
  parsedDate: string;
  relationId: string;
  fixedSentimentApplicable: boolean;
  relatedCompany: string[];
  chainOfThought: string;
  confidenceScore: number;
  sentimentLabel: string;
  rawSentimentScore: number;
  positiveProb: number;
  negativeProb: number;
  neutralProb: number;
  ontologySentiment: number;
}

export interface OhlcvBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface PredictionBar {
  signal: string;
  probabilityUp: number;
}

export interface StockAnalysisPayload {
  type: "stock_analysis";
  ticker: string;
  signal: string;
  probabilityUp: number;
  priceSummary: Record<string, number>;
  priceDates: string[];
  priceDfDict: Array<Record<string, number>>;
  sentimentDfDict: Array<Record<string, number>>;
  dailySentiment: Record<string, { sentimentMean: number; newsCount: number }>;
  newsItems: NewsItemPayload[];
  rawNews: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
  ohlcvData: OhlcvBar[];
  predictionBar: PredictionBar;
}

export type DashboardPayload =
  | MarketDiscoveryPayload
  | ChartPayload
  | CodePayload
  | CompanyInfoPayload
  | SectorPayload
  | StockAnalysisPayload
  | null;

// ── API Request / Response ──────────────────────────────────────────────────────

export type ChatMode = "none" | "market_discovery" | "stock_deep_analysis";

export interface ChatHistoryItem {
  role: MessageRole;
  content: string;
  images?: string[];
}

export interface ChatRequest {
  history: ChatHistoryItem[];
  mode: ChatMode;
}

// Legacy response (from POST /api/chat)
export interface ChatResponse {
  reply_text: string;
  dashboard_payload: DashboardPayload;
}

// V2 response (from POST /api/chat/stream final event)
export interface ChatResponseV2 {
  replyText: string;
  dashboardPayload: DashboardPayload;
  thinkingSteps: ThinkingStep[];
  modeUsed: "company_info" | "sector_analysis" | "stock_analysis" | "none";
}
