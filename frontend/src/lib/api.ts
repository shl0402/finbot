// frontend/src/lib/api.ts
import type {
  ChatResponse,
  DashboardPayload,
  ChartPayload,
  MarketDiscoveryPayload,
  CodePayload,
  MetricCard,
  ChartPoint,
  ChatMode,
  ChatHistoryItem,
} from "@/types/chat";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** FastAPI/Pydantic returns snake_case keys; normalize to frontend camelCase. */
function normalizeMetricCard(m: Record<string, unknown>): MetricCard {
  return {
    label: String(m.label ?? ""),
    value: String(m.value ?? ""),
    delta: m.delta != null ? String(m.delta) : undefined,
    deltaColor: (m.delta_color ?? m.deltaColor) as MetricCard["deltaColor"],
  };
}

function normalizeDashboardPayload(raw: unknown): DashboardPayload {
  if (raw == null || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const t = o.type;

  if (t === "metrics") {
    const metricsRaw = o.metrics;
    const metrics = Array.isArray(metricsRaw)
      ? metricsRaw.map((x) => normalizeMetricCard(x as Record<string, unknown>))
      : [];
    const rawRR = o.rr_score ?? o.rrScore;
    const rrScore =
      rawRR && typeof rawRR === "object"
        ? { ratio: String((rawRR as Record<string, unknown>).ratio ?? ""), description: String((rawRR as Record<string, unknown>).description ?? "") }
        : undefined;
    return {
      type: "metrics",
      symbol: String(o.symbol ?? ""),
      name: String(o.name ?? ""),
      metrics,
      rrScore,
    } satisfies MarketDiscoveryPayload;
  }

  if (t === "chart") {
    const rawData = (o.chart_data ?? o.chartData) as unknown;
    const chartData = Array.isArray(rawData) ? (rawData as ChartPoint[]) : [];

    const rawKeyStats = o.key_stats ?? o.keyStats;
    const keyStats = Array.isArray(rawKeyStats)
      ? rawKeyStats.map((x: unknown) => normalizeMetricCard(x as Record<string, unknown>))
      : undefined;

    const rawWordCloud = o.word_cloud ?? o.wordCloud;
    const wordCloud = Array.isArray(rawWordCloud) ? rawWordCloud as Array<{ word: string; score: number; size: number }> : undefined;

    const rawTopPos = o.top_positive ?? o.topPositive;
    const topPositive = Array.isArray(rawTopPos) ? rawTopPos as Array<{ word: string; count: number }> : undefined;

    const rawTopNeg = o.top_negative ?? o.topNegative;
    const topNegative = Array.isArray(rawTopNeg) ? rawTopNeg as Array<{ word: string; count: number }> : undefined;

    return {
      type: "chart",
      symbol: String(o.symbol ?? ""),
      name: String(o.name ?? ""),
      chartData,
      keyStats,
      sentimentScore: o.sentiment_score != null ? Number(o.sentiment_score) : undefined,
      sentimentLabel: o.sentiment_label != null ? String(o.sentiment_label) : undefined,
      wordCloud,
      topPositive,
      topNegative,
      newsCount: o.news_count != null ? Number(o.news_count) : undefined,
    } satisfies ChartPayload;
  }

  if (t === "code") {
    return {
      type: "code",
      language: String(o.language ?? ""),
      code: String(o.code ?? ""),
      description: String(o.description ?? ""),
    } satisfies CodePayload;
  }

  return null;
}

export async function sendChat(
  history: ChatHistoryItem[],
  mode: ChatMode = "none"
): Promise<ChatResponse> {
  console.log("[sendChat] →", JSON.stringify(history.map((h) => ({ ...h, images: h.images?.length }))), "| mode:", mode);
  const res = await fetch(`${BASE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ history, mode }),
  });
  console.log("[sendChat] ← status:", res.status);
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  const json: Record<string, unknown> = await res.json();
  return {
    reply_text: String(json.reply_text ?? ""),
    dashboard_payload: normalizeDashboardPayload(json.dashboard_payload),
  };
}
