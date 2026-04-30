// frontend/src/lib/api.ts

import type {
  ChatResponse,
  ChatResponseV2,
  DashboardPayload,
  ChartPayload,
  MarketDiscoveryPayload,
  CodePayload,
  CompanyInfoPayload,
  SectorPayload,
  MetricCard,
  ChartPoint,
  ChatMode,
  ChatHistoryItem,
  ThinkingStep,
  StockAnalysisPayload,
} from "@/types/chat";
import { logger } from "./logger";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Normalizers ────────────────────────────────────────────────────────────────

function normalizeMetricCard(m: Record<string, unknown>): MetricCard {
  return {
    label: String(m.label ?? ""),
    value: String(m.value ?? ""),
    delta: m.delta != null ? String(m.delta) : undefined,
    deltaColor: (m.delta_color ?? m.deltaColor) as MetricCard["deltaColor"],
  };
}

function normalizeCompanyInfo(o: Record<string, unknown>): CompanyInfoPayload {
  const rawStats = o.stats;
  const stats = Array.isArray(rawStats)
    ? rawStats.map((x) => normalizeMetricCard(x as Record<string, unknown>))
    : [];

  const rawProfile = o.profile;
  const profile: Record<string, string> =
    rawProfile && typeof rawProfile === "object"
      ? Object.fromEntries(
          Object.entries(rawProfile as Record<string, unknown>).map(([k, v]) => [
            k,
            String(v ?? ""),
          ])
        )
      : {};

  return {
    type: "company_info",
    companyName: String(o.company_name ?? o.companyName ?? ""),
    symbol: String(o.symbol ?? ""),
    price: String(o.price ?? ""),
    change: String(o.change ?? ""),
    changePercent: String(o.change_percent ?? o.changePercent ?? ""),
    marketCap: String(o.market_cap ?? o.marketCap ?? ""),
    peRatio: String(o.pe_ratio ?? o.peRatio ?? ""),
    description: String(o.description ?? ""),
    stats,
    profile,
  };
}

function normalizeSectorItem(raw: Record<string, unknown>): Record<string, unknown> {
  return {
    sector: String(raw.sector ?? ""),
    changePercent: String(raw.change_percent ?? ""),
    link: String(raw.link ?? ""),
    // snake_case from backend -> camelCase
    marketCap: raw.market_cap ?? raw.marketCap,
    dividendYield: raw.dividend_yield ?? raw.dividendYield,
    volume: raw.volume,
    industriesCount: raw.industries_count ?? raw.industriesCount,
    stocksCount: raw.stocks_count ?? raw.stocksCount,
    perf1w: raw.perf_1w ?? raw.perf1w,
    perf1m: raw.perf_1m ?? raw.perf1m,
    perf3m: raw.perf_3m ?? raw.perf3m,
    perf6m: raw.perf_6m ?? raw.perf6m,
    perfYtd: raw.perf_ytd ?? raw.perfYtd,
    perf1y: raw.perf_1y ?? raw.perf1y,
    perf5y: raw.perf_5y ?? raw.perf5y,
    perf10y: raw.perf_10y ?? raw.perf10y,
    perfAllTime: raw.perf_all_time ?? raw.perfAllTime,
  };
}

function normalizeSectorPayload(o: Record<string, unknown>): SectorPayload {
  const rawSectors = o.sectors as Array<Record<string, unknown>> | undefined;
  const sectors = Array.isArray(rawSectors)
    ? (rawSectors.map((x) => normalizeSectorItem(x)) as unknown as SectorPayload["sectors"])
    : [];

  return {
    type: "sector",
    source: (o.source as SectorPayload["source"]) ?? "futunn",
    interactive: Boolean(o.interactive ?? false),
    sectors,
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
        ? {
            ratio: String((rawRR as Record<string, unknown>).ratio ?? ""),
            description: String((rawRR as Record<string, unknown>).description ?? ""),
          }
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
    const rawData = o.chart_data ?? o.chartData;
    const chartData = Array.isArray(rawData) ? (rawData as ChartPoint[]) : [];
    const rawKeyStats = o.key_stats ?? o.keyStats;
    const keyStats = Array.isArray(rawKeyStats)
      ? rawKeyStats.map((x) => normalizeMetricCard(x as Record<string, unknown>))
      : undefined;
    const rawWordCloud = o.word_cloud ?? o.wordCloud;
    const wordCloud = Array.isArray(rawWordCloud)
      ? (rawWordCloud as Array<{ word: string; score: number; size: number }>)
      : undefined;
    const rawTopPos = o.top_positive ?? o.topPositive;
    const topPositive = Array.isArray(rawTopPos)
      ? (rawTopPos as Array<{ word: string; count: number }>)
      : undefined;
    const rawTopNeg = o.top_negative ?? o.topNegative;
    const topNegative = Array.isArray(rawTopNeg)
      ? (rawTopNeg as Array<{ word: string; count: number }>)
      : undefined;
    return {
      type: "chart",
      symbol: String(o.symbol ?? ""),
      name: String(o.name ?? ""),
      chartData,
      keyStats,
      sentimentScore:
        o.sentiment_score != null ? Number(o.sentiment_score) : undefined,
      sentimentLabel:
        o.sentiment_label != null ? String(o.sentiment_label) : undefined,
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

  if (t === "company_info") {
    return normalizeCompanyInfo(o);
  }

  if (t === "sector") {
    return normalizeSectorPayload(o);
  }

  if (t === "stock_analysis") {
    const rawNewsItems = o.news_items;
    const newsItems = Array.isArray(rawNewsItems)
      ? rawNewsItems.map((n: Record<string, unknown>) => ({
          title: String(n.title ?? ""),
          time: String(n.time ?? ""),
          source: String(n.source ?? ""),
          link: String(n.link ?? ""),
          shortDescription: String(n.short_description ?? ""),
          parsedDate: String(n.parsed_date ?? ""),
          relationId: String(n.relation_id ?? "0.0"),
          fixedSentimentApplicable: Boolean(n.fixed_sentiment_applicable ?? false),
          relatedCompany: Array.isArray(n.related_company) ? n.related_company.map(String) : [],
          chainOfThought: String(n.chain_of_thought ?? ""),
          confidenceScore: Number(n.confidence_score ?? 0),
          sentimentLabel: String(n.sentiment_label ?? "neutral"),
          rawSentimentScore: Number(n.raw_sentiment_score ?? 0),
          positiveProb: Number(n.positive_prob ?? 0),
          negativeProb: Number(n.negative_prob ?? 0),
          neutralProb: Number(n.neutral_prob ?? 0),
          ontologySentiment: Number(n.ontology_sentiment ?? 0),
        }))
      : [];

    const rawOhlcv = o.ohlcv_data ?? o.ohlcvData ?? [];
    const ohlcvData = Array.isArray(rawOhlcv)
      ? rawOhlcv.map((b: Record<string, unknown>) => ({
          date: String(b.date ?? ""),
          open: Number(b.open ?? 0),
          high: Number(b.high ?? 0),
          low: Number(b.low ?? 0),
          close: Number(b.close ?? 0),
          volume: Number(b.volume ?? 0),
        }))
      : [];

    const rawPred = (o.prediction_bar ?? o.predictionBar ?? {}) as Record<string, unknown>;
    const predictionBar = {
      signal: String(rawPred.signal ?? o.signal ?? ""),
      probabilityUp: Number(rawPred.probability_up ?? rawPred.probabilityUp ?? o.probability_up ?? o.probabilityUp ?? 0),
    };

    return {
      type: "stock_analysis",
      ticker: String(o.ticker ?? ""),
      signal: String(o.signal ?? ""),
      probabilityUp: Number(o.probability_up ?? o.probabilityUp ?? 0),
      priceSummary: (o.price_summary ?? o.priceSummary ?? {}) as Record<string, number>,
      priceDates: Array.isArray(o.price_dates ?? o.priceDates) ? (o.price_dates ?? o.priceDates) as string[] : [],
      priceDfDict: Array.isArray(o.price_df_dict ?? o.priceDfDict) ? (o.price_df_dict ?? o.priceDfDict) as Array<Record<string, number>> : [],
      sentimentDfDict: Array.isArray(o.sentiment_df_dict ?? o.sentimentDfDict) ? (o.sentiment_df_dict ?? o.sentimentDfDict) as Array<Record<string, number>> : [],
      dailySentiment: (() => {
        const raw = (o.daily_sentiment ?? o.dailySentiment ?? {}) as Record<string, Record<string, unknown>>;
        const result: Record<string, { sentimentMean: number; newsCount: number }> = {};
        for (const [date, vals] of Object.entries(raw)) {
          result[date] = {
            sentimentMean: Number(vals.sentiment_mean ?? vals.sentimentMean ?? 0),
            newsCount: Number(vals.news_count ?? vals.newsCount ?? 0),
          };
        }
        return result;
      })(),
      newsItems,
      rawNews: Array.isArray(o.raw_news ?? o.rawNews) ? (o.raw_news ?? o.rawNews) as Array<Record<string, unknown>> : [],
      metadata: (o.metadata ?? {}) as Record<string, unknown>,
      ohlcvData,
      predictionBar,
    } satisfies StockAnalysisPayload;
  }

  return null;
}

// ── Normalize ThinkingStep (snake_case -> camelCase) ───────────────────────────

function normalizeThinkingStep(raw: Record<string, unknown>): ThinkingStep {
  return {
    stepNumber: Number(raw.step_number ?? raw.stepNumber ?? 0),
    phase: (raw.phase ?? "intent_routing") as ThinkingStep["phase"],
    status: (raw.status ?? "active") as ThinkingStep["status"],
    content: String(raw.content ?? ""),
    toolUsed: String(raw.tool_used ?? raw.toolUsed ?? ""),
    toolResultPreview:
      String(raw.tool_result_preview ?? raw.toolResultPreview ?? ""),
  };
}

// ── SSE Streaming ───────────────────────────────────────────────────────────────

/**
 * Send a chat request with SSE streaming.
 * onStep   — called for every SSE step event
 * onComplete — called when the final "response" event arrives
 * onError   — called on network/parse errors
 */
export function sendChatStream(
  history: ChatHistoryItem[],
  onStep: (step: ThinkingStep) => void,
  onComplete: (response: ChatResponseV2) => void,
  onError: (err: Error) => void
): () => void {
  logger.info("sendChatStream called — history_len=%d BASE_URL=%s", history.length, BASE_URL);

  const controller = new AbortController();
  let done = false;

  const fetchUrl = `${BASE_URL}/api/chat/stream`;
  logger.debug("SSE fetch initiating — url=%s", fetchUrl);

  fetch(fetchUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ history, mode: "none" }),
    signal: controller.signal,
  })
    .then(async (res) => {
      logger.debug("SSE fetch response — status=%d ok=%s", res.status, res.ok);
      if (!res.ok) {
        throw new Error(`Server error: ${res.status}`);
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done: readerDone, value } = await reader.read();
        if (readerDone) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events properly: each event ends with a blank line (\n\n).
        // Accumulate lines until we hit a blank line, then dispatch the complete event.
        while (buffer.includes("\n\n")) {
          const eventEnd = buffer.indexOf("\n\n");
          const eventBlock = buffer.slice(0, eventEnd);
          buffer = buffer.slice(eventEnd + 2);

          // Extract the data: line(s) — could be multi-line if JSON contains newlines
          const dataLine = eventBlock
            .split("\n")
            .map((l) => l.trim())
            .find((l) => l.startsWith("data: "));

          if (!dataLine) continue;

          const payload = dataLine.slice("data: ".length).trim();
          if (!payload) continue;

          try {
            const event = JSON.parse(payload) as {
              type: string;
              data: unknown;
            };

            if (event.type === "step") {
              const step = normalizeThinkingStep(event.data as Record<string, unknown>);
              logger.debug("SSE step: phase=%s status=%s", step.phase, step.status);
              onStep(step);
            } else if (event.type === "response") {
              const data = event.data as Record<string, unknown>;
              const thinkingStepsRaw = data.thinking_steps as unknown[];
              const thinkingSteps: ThinkingStep[] = Array.isArray(thinkingStepsRaw)
                ? thinkingStepsRaw.map((x) =>
                    normalizeThinkingStep(x as Record<string, unknown>)
                  )
                : [];
              const response: ChatResponseV2 = {
                replyText: String(data.reply_text ?? data.replyText ?? ""),
                dashboardPayload: normalizeDashboardPayload(
                  data.dashboard_payload ?? data.dashboardPayload
                ),
                thinkingSteps,
                modeUsed: (data.mode_used ?? data.modeUsed ?? "none") as ChatResponseV2["modeUsed"],
              };
              logger.info("SSE complete — reply_len=%d", response.replyText.length);
              onComplete(response);
              done = true;
            } else if (event.type === "error") {
              logger.error("SSE error event:", event.data);
              onError(new Error(String(event.data)));
            }
          } catch (parseErr) {
            logger.warn("Failed to parse SSE line: %s", payload.slice(0, 500), parseErr);
          }
        }
      }
    })
    .catch((err) => {
      logger.debug("SSE fetch catch — err.name=%s err.message=%s", err.name, err.message);
      if (err.name !== "AbortError") {
        logger.error("sendChatStream fetch error:", err);
        onError(err);
      }
    });

  // Return abort function
  return () => {
    if (!done) {
      controller.abort();
    }
  };
}

// ── Legacy non-streaming sendChat ───────────────────────────────────────────────

export async function sendChat(
  history: ChatHistoryItem[],
  mode: ChatMode = "none"
): Promise<ChatResponse> {
  logger.info("sendChat (legacy) — history_len=%d mode=%s", history.length, mode);
  const res = await fetch(`${BASE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ history, mode }),
  });
  logger.info("sendChat ← status=%d", res.status);
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  const json: Record<string, unknown> = await res.json();
  return {
    reply_text: String(json.reply_text ?? ""),
    dashboard_payload: normalizeDashboardPayload(json.dashboard_payload),
  };
}
