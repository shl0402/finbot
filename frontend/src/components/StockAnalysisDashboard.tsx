"use client";

import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { createChart, ColorType, CrosshairMode, CandlestickSeries, HistogramSeries, LineSeries } from "lightweight-charts";
import { X, ExternalLink, ChevronDown, ChevronUp, TrendingUp, TrendingDown } from "lucide-react";
import type { StockAnalysisPayload, NewsItemPayload, OhlcvBar } from "@/types/chat";

interface StockAnalysisDashboardProps {
  payload: StockAnalysisPayload;
  onClose: () => void;
}

// ── Ontology Relation Map (code → { name, description }) ──────────────────────
// Hardcoded from the ontology defined in backend/tools/stock_analysis.py SYSTEM_PROMPT
const ONTOLOGY_MAP: Record<string, { name: string; description: string }> = {
  "0.0": {
    name: "No Relation / Noise",
    description: "The news does not fit the ontology, lacks actionable connection, or is purely retrospective summary.",
  },
  "0.1": {
    name: "Direct Fundamental",
    description: "Earnings reports, guidance updates, product launches, or management changes directly at the target company.",
  },
  "0.2": {
    name: "Direct Regulatory/Legal",
    description: "The target company wins/loses a lawsuit, faces fines, or receives direct government approval.",
  },
  "0.3": {
    name: "Corporate Action",
    description: "Stock splits, buybacks, or dividend announcements.",
  },
  "0.4": {
    name: "Analyst/Brokerage Rating",
    description: "Upgrades, downgrades, price target adjustments, or initiation of coverage by investment banks and research firms.",
  },
  "1.1": {
    name: "Zero-Sum Catalyst",
    description: "Competitor captures a finite resource (contract, patent, exclusive rights).",
  },
  "1.2": {
    name: "Sector Tailwind/Headwind",
    description: "A peer proves a macro trend that lifts/drags the whole sector.",
  },
  "1.3": {
    name: "Capacity/Supply Destruction",
    description: "A peer suffers a factory fire, ban, or bankruptcy (Target gains market share).",
  },
  "1.4": {
    name: "Substitution Threat",
    description: "An adjacent industry creates a cheaper/better alternative to the target's product.",
  },
  "2.1": {
    name: "Upstream Breakthrough/Expansion",
    description: "Supplier invents a cheaper process or expands capacity.",
  },
  "2.2": {
    name: "Upstream Supply Shock",
    description: "Supplier faces shortages, strikes, or tariffs.",
  },
  "2.3": {
    name: "Downstream Demand Shock",
    description: "Major buyer sees a massive surge/drop in end-user sales.",
  },
  "2.4": {
    name: "Downstream Insolvency/Churn",
    description: "Major client goes bankrupt or switches to a competitor.",
  },
  "3.1": {
    name: "Complementary Goods",
    description: "Products bought together (e.g., EVs and Charging Stations).",
  },
  "3.2": {
    name: "Strategic Partners/JV",
    description: "Explicit R&D, distribution, or marketing partnerships.",
  },
  "4.1": {
    name: "Institutional Capital Flow",
    description: "Significant buying/selling by funds (e.g., Southbound Capital, Hedge Funds).",
  },
  "4.2": {
    name: "Index/ETF Inclusion",
    description: "The target is added to or removed from a major market index.",
  },
};

function sentimentColor(label: string): string {
  switch (label) {
    case "positive": return "text-green-400 bg-green-400/15 border-green-400/30";
    case "negative": return "text-red-400 bg-red-400/15 border-red-400/30";
    default:          return "text-zinc-400 bg-zinc-400/15 border-zinc-400/30";
  }
}

function relationBadge(relId: string): string {
  if (relId === "0.0" || relId === "0") return "text-zinc-500 bg-zinc-500/10";
  if (relId.startsWith("0.")) return "text-blue-400 bg-blue-400/15 border-blue-400/30";
  if (relId.startsWith("1.")) return "text-amber-400 bg-amber-400/15 border-amber-400/30";
  if (relId.startsWith("2.")) return "text-purple-400 bg-purple-400/15 border-purple-400/30";
  if (relId.startsWith("3.")) return "text-cyan-400 bg-cyan-400/15 border-cyan-400/30";
  if (relId.startsWith("4.")) return "text-pink-400 bg-pink-400/15 border-pink-400/30";
  return "text-zinc-400 bg-zinc-400/15";
}

function RelationBadge({ relId }: { relId: string }) {
  const [visible, setVisible] = useState(false);
  const [mouseX, setMouseX] = useState(0);
  const [mouseY, setMouseY] = useState(0);
  const info = ONTOLOGY_MAP[relId];
  const badgeClass = relationBadge(relId);

  const tooltip = visible && info ? (
    <div
      className="fixed z-[9999] w-72 rounded-lg border border-white/15 bg-[#2a2a2c] p-2 shadow-xl"
      style={{
        top: mouseY + 12,
        left: mouseX + 12,
        pointerEvents: "none",
      }}
    >
      <p className="text-[10px] font-semibold text-zinc-200 mb-0.5">{info.name}</p>
      <p className="text-[10px] text-zinc-400 leading-relaxed">{info.description}</p>
    </div>
  ) : null;

  return (
    <>
      <span
        className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[9px] font-mono cursor-help ${badgeClass}`}
        onMouseEnter={(e) => {
          setVisible(true);
          setMouseX(e.clientX);
          setMouseY(e.clientY);
        }}
        onMouseMove={(e) => {
          setMouseX(e.clientX);
          setMouseY(e.clientY);
        }}
        onMouseLeave={() => setVisible(false)}
      >
        <span>{relId}</span>
        {info && (
          <span className="ml-1 text-[8px] opacity-75">({info.name})</span>
        )}
      </span>
      {tooltip && createPortal(tooltip, document.body)}
    </>
  );
}

function NewsItemCard({ item }: { item: NewsItemPayload }) {
  const [expanded, setExpanded] = useState(false);
  const sentColor = sentimentColor(item.sentimentLabel);

  return (
    <div className="rounded-xl border border-white/[0.06] bg-[#1e1e20] overflow-hidden transition-all hover:border-white/[0.1]">
      {/* Collapsed header — always visible */}
      <button
        className="w-full flex items-start gap-2 p-3 text-left"
        onClick={() => setExpanded((e) => !e)}
      >
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-zinc-100 leading-tight line-clamp-2">
            {item.title}
          </p>
          <div className="flex flex-wrap items-center gap-2 mt-1.5">
            <span className="text-[10px] text-zinc-500">{item.time}</span>
            <span className="text-[10px] text-zinc-600">·</span>
            <span className="text-[10px] text-zinc-600">{item.source}</span>
            <RelationBadge relId={item.relationId} />
            <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[9px] ${sentColor}`}>
              {item.sentimentLabel}
            </span>
          </div>
        </div>
        <div className="flex-shrink-0 text-zinc-500 mt-0.5">
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </button>

      {/* Expanded details */}
      {expanded && (
        <div className="px-3 pb-3 border-t border-white/[0.04] pt-2 space-y-2">
          {item.link && (
            <a
              href={item.link}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300"
            >
              Read full article <ExternalLink size={10} />
            </a>
          )}

          {item.chainOfThought && (
            <div className="rounded-lg bg-black/20 border border-white/[0.04] p-2">
              <p className="text-[9px] text-zinc-600 uppercase tracking-wide mb-1">Chain of Thought</p>
              <p className="text-[11px] text-zinc-300 leading-relaxed">{item.chainOfThought}</p>
            </div>
          )}

          {item.relatedCompany && item.relatedCompany.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[9px] text-zinc-600 uppercase tracking-wide">Entities:</span>
              {item.relatedCompany.map((c, i) => (
                <span key={i} className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] text-zinc-300">
                  {c}
                </span>
              ))}
            </div>
          )}

          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            <div className="flex justify-between">
              <span className="text-[10px] text-zinc-500">Confidence</span>
              <span className="text-[10px] text-zinc-300 font-mono">{item.confidenceScore.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[10px] text-zinc-500">Ontology Score</span>
              <span className={`text-[10px] font-mono ${item.ontologySentiment >= 0 ? "text-green-400" : "text-red-400"}`}>
                {item.ontologySentiment.toFixed(3)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-[10px] text-zinc-500">Positive Prob</span>
              <span className="text-[10px] text-green-400 font-mono">{item.positiveProb.toFixed(3)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[10px] text-zinc-500">Negative Prob</span>
              <span className="text-[10px] text-red-400 font-mono">{item.negativeProb.toFixed(3)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[10px] text-zinc-500">Neutral Prob</span>
              <span className="text-[10px] text-zinc-400 font-mono">{item.neutralProb.toFixed(3)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[10px] text-zinc-500">Fixed Sentiment</span>
              <span className="text-[10px] text-zinc-300">{item.fixedSentimentApplicable ? "Yes" : "No"}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function DailySentimentBar({ date, sentimentMean, newsCount }: { date: string; sentimentMean: number; newsCount: number }) {
  const pct = Math.min(Math.abs(sentimentMean), 1);
  const isPositive = sentimentMean >= 0;
  const barColor = isPositive ? "bg-green-500" : "bg-red-500";
  const barWidth = (pct * 100).toFixed(1);

  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-zinc-500 w-20 flex-shrink-0">{date}</span>
      <div className="flex-1 relative h-3 rounded-full bg-white/5 overflow-hidden">
        <div
          className={`absolute h-full rounded-full ${barColor}`}
          style={{
            width: `${barWidth}%`,
            ...(isPositive ? { left: "50%" } : { right: "50%" }),
          }}
        />
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-[9px] text-zinc-400 font-mono">{sentimentMean.toFixed(3)}</span>
        </div>
      </div>
      <span className="text-[10px] text-zinc-600 w-6 text-right">{newsCount}</span>
    </div>
  );
}

export default function StockAnalysisDashboard({ payload, onClose }: StockAnalysisDashboardProps) {
  const { ticker, signal, probabilityUp, priceSummary, ohlcvData, predictionBar, priceDates, priceDfDict, dailySentiment, newsItems, metadata } = payload;

  const [newsExpanded, setNewsExpanded] = useState(false);
  const [sentimentExpanded, setSentimentExpanded] = useState(false);
  const [tooltip, setTooltip] = useState<{ date: string; bar: OhlcvBar | null; x: number; y: number } | null>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const chartContainerRef = useRef<HTMLDivElement>(null);

  const isBuy = signal === "BUY";
  const probPct = (probabilityUp * 100).toFixed(1);

  const sortedDays = Object.entries(dailySentiment)
    .sort(([a], [b]) => b.localeCompare(a))
    .slice(0, sentimentExpanded ? undefined : 7);

  // ── Candlestick Chart ───────────────────────────────────────────────────────

  useEffect(() => {
    if (!chartContainerRef.current || !ohlcvData || ohlcvData.length === 0) return;

    // Clean up previous chart instance
    let chart: ReturnType<typeof createChart> | null = null;

    const container = chartContainerRef.current;

    try {
      chart = createChart(container, {
        layout: {
          background: { type: ColorType.Solid, color: "#1a1a1b" },
          textColor: "#71717a",
          fontSize: 10,
          attributionLogo: false,
        },
        grid: {
          vertLines: { color: "#27272a" },
          horzLines: { color: "#27272a" },
        },
        crosshair: {
          mode: CrosshairMode.Normal,
          vertLine: { color: "#52525b", labelBackgroundColor: "#3f3f46" },
          horzLine: { color: "#52525b", labelBackgroundColor: "#3f3f46" },
        },
        rightPriceScale: {
          borderColor: "#3f3f46",
          scaleMargins: { top: 0.1, bottom: 0.2 },
        },
        timeScale: {
          borderColor: "#3f3f46",
          timeVisible: true,
          secondsVisible: false,
        },
        width: container.clientWidth,
        height: 220,
        handleScroll: { mouseWheel: true, pressedMouseMove: true },
        handleScale: { mouseWheel: true, pinch: true },
      });

      // Historical candlestick series (v5 API: chart.addSeries(CandlestickSeries, options))
      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: "#22c55e",
        downColor: "#ef4444",
        borderUpColor: "#22c55e",
        borderDownColor: "#ef4444",
        wickUpColor: "#22c55e",
        wickDownColor: "#ef4444",
      });

      const candleData = ohlcvData.map((bar) => ({
        time: bar.date,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      }));
      candleSeries.setData(candleData);

      // Volume histogram
      const volSeries = chart.addSeries(HistogramSeries, {
        color: "#52525b",
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
      });
      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.85, bottom: 0 },
      });
      const volData = ohlcvData.map((bar) => ({
        time: bar.date,
        value: bar.volume,
        color: bar.close >= bar.open ? "#22c55e33" : "#ef444433",
      }));
      volSeries.setData(volData);

      // Prediction arrow: draw dashed line from last close to predicted close one day ahead
      if (predictionBar && predictionBar.signal && ohlcvData.length > 0) {
        const lastBar = ohlcvData[ohlcvData.length - 1];
        const lastClose = lastBar.close;
        const probUp = predictionBar.probabilityUp;
        const direction = predictionBar.signal === "BUY" ? 1 : -1;
        const movePct = probUp * 0.04;
        const predictedClose = lastClose * (1 + direction * movePct);

        // Next business day (skip weekends)
        const nextDate = new Date(lastBar.date);
        nextDate.setDate(nextDate.getDate() + 3);
        if (nextDate.getDay() === 0) nextDate.setDate(nextDate.getDate() + 1);
        else if (nextDate.getDay() === 6) nextDate.setDate(nextDate.getDate() + 2);
        const nextDateStr = nextDate.toISOString().split("T")[0];

        const predSeries = chart.addSeries(LineSeries, {
          color: predictionBar.signal === "BUY" ? "#22c55e" : "#ef4444",
          lineWidth: 2,
          lineStyle: 2,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });

        predSeries.setData([
          { time: lastBar.date, value: lastClose },
          { time: nextDateStr, value: predictedClose },
        ]);

        // Arrow annotation via price line
        const priceLine = predSeries.createPriceLine({
          price: predictedClose,
          color: predictionBar.signal === "BUY" ? "#22c55e" : "#ef4444",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: predictionBar.signal === "BUY" ? "PREDICT \u2191" : "PREDICT \u2193",
        });
      }

      // Tooltip on crosshair move
      chart.subscribeCrosshairMove((param) => {
        if (!param.time || !param.point) {
          setTooltip(null);
          return;
        }
        const bar = ohlcvData.find((b) => b.date === param.time);
        if (bar) {
          setTooltip({
            date: bar.date,
            bar,
            x: param.point.x,
            y: param.point.y,
          });
        } else {
          setTooltip(null);
        }
      });

      // Resize observer
      const resizeObserver = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const { width } = entry.contentRect;
          chart?.applyOptions({ width });
          setContainerWidth(width);
        }
      });
      resizeObserver.observe(container);

      return () => {
        resizeObserver.disconnect();
        if (chart) {
          chart.remove();
        }
      };
    } catch (err) {
      console.error("[CandlestickChart] init error:", err);
      if (chart) chart.remove();
    }
  }, [ohlcvData, predictionBar]);

  return (
    <div className="flex flex-shrink-0 flex-col border-l border-white/[0.08] bg-[#131314] h-full overflow-hidden">

      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.08] px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-5 w-5 items-center justify-center rounded bg-gradient-to-br from-green-400 to-red-500">
            <div className="h-2.5 w-2.5 rounded-sm bg-white/80" />
          </div>
          <div>
            <p className="text-sm font-medium text-zinc-100">Stock Analysis</p>
            <p className="text-[11px] text-zinc-500">ticker: {ticker}</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="rounded-full p-1 text-zinc-500 transition-colors hover:bg-white/10 hover:text-zinc-200"
        >
          <X size={14} />
        </button>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto">

        {/* Signal Banner */}
        <div className="px-4 py-4 border-b border-white/[0.06]">
          <div className={`flex items-center gap-3 rounded-2xl p-4 border ${
            isBuy
              ? "bg-green-500/10 border-green-500/30"
              : "bg-red-500/10 border-red-500/30"
          }`}>
            <div className={`flex h-12 w-12 items-center justify-center rounded-full ${
              isBuy ? "bg-green-500/20" : "bg-red-500/20"
            }`}>
              {isBuy ? <TrendingUp size={24} className="text-green-400" /> : <TrendingDown size={24} className="text-red-400" />}
            </div>
            <div>
              <p className={`text-3xl font-bold tracking-tight ${isBuy ? "text-green-400" : "text-red-400"}`}>
                {signal}
              </p>
              <p className={`text-sm font-semibold ${isBuy ? "text-green-300/70" : "text-red-300/70"}`}>
                {probPct}% probability of upside
              </p>
            </div>
          </div>

          {/* Price Summary Pills */}
          <div className="flex flex-wrap gap-2 mt-3">
            {Object.entries(priceSummary).map(([key, val]) => (
              <div key={key} className="rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-1.5">
                <p className="text-[9px] text-zinc-600 uppercase tracking-wide leading-none mb-0.5">{key.replace(/_/g, " ")}</p>
                <p className="text-xs font-semibold text-zinc-200 font-mono leading-none">{
                  key === "close" || key === "vwap"
                    ? `$${Number(val).toFixed(2)}`
                    : key === "Volume"
                    ? Number(val).toLocaleString()
                    : Number(val).toFixed(4)
                }</p>
              </div>
            ))}
          </div>
        </div>

        {/* Candlestick Chart */}
        <div className="px-4 py-3 border-b border-white/[0.06]">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-zinc-300">Price Chart (20-day lookback)</h3>
            {ohlcvData.length > 0 && (
              <span className="text-[10px] text-zinc-600">
                {ohlcvData[0].date} → {ohlcvData[ohlcvData.length - 1].date}
              </span>
            )}
          </div>
          <div className="relative rounded-xl border border-white/[0.06] overflow-hidden" style={{ background: "#1a1a1b" }}>
            {ohlcvData.length > 0 ? (
              <>
                {/* Chart container */}
                <div ref={chartContainerRef} className="w-full" style={{ height: 220 }} />

                {/* OHLCV Tooltip overlay */}
                {tooltip && tooltip.bar && (
                  <div
                    className="absolute pointer-events-none z-20 rounded-lg border border-white/[0.1] bg-[#1e1e20] px-3 py-2 shadow-xl"
                    style={{
                      left: Math.min(tooltip.x + 12, (containerWidth || 400) - 200),
                      top: Math.max(tooltip.y - 60, 4),
                    }}
                  >
                    <p className="text-[10px] font-medium text-zinc-300 mb-1.5">{tooltip.bar.date}</p>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                      <span className="text-[9px] text-zinc-500">Open</span>
                      <span className="text-[10px] text-zinc-200 font-mono text-right">${tooltip.bar.open.toFixed(2)}</span>
                      <span className="text-[9px] text-zinc-500">High</span>
                      <span className="text-[10px] text-green-400 font-mono text-right">${tooltip.bar.high.toFixed(2)}</span>
                      <span className="text-[9px] text-zinc-500">Low</span>
                      <span className="text-[10px] text-red-400 font-mono text-right">${tooltip.bar.low.toFixed(2)}</span>
                      <span className="text-[9px] text-zinc-500">Close</span>
                      <span className={`text-[10px] font-mono text-right ${tooltip.bar.close >= tooltip.bar.open ? "text-green-400" : "text-red-400"}`}>
                        ${tooltip.bar.close.toFixed(2)}
                      </span>
                      <span className="text-[9px] text-zinc-500">Volume</span>
                      <span className="text-[10px] text-zinc-400 font-mono text-right">{tooltip.bar.volume.toLocaleString()}</span>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="flex items-center justify-center h-48 text-zinc-600 text-xs">
                No price data available
              </div>
            )}
          </div>
          {predictionBar && predictionBar.signal && ohlcvData.length > 0 && (
            <div className="flex items-center gap-2 mt-2">
              <span className="text-[10px] text-zinc-600">Next day prediction:</span>
              <span className={`inline-flex items-center gap-1 text-[10px] font-semibold ${predictionBar.signal === "BUY" ? "text-green-400" : "text-red-400"}`}>
                {predictionBar.signal === "BUY" ? "↑" : "↓"} {(predictionBar.probabilityUp * 100).toFixed(1)}% confidence
              </span>
            </div>
          )}
        </div>

        {/* Price Features Table */}
        <div className="px-4 py-3 border-b border-white/[0.06]">
          <div className="rounded-xl border border-white/[0.06] overflow-hidden">
            <div className="overflow-x-auto max-h-40">
              <table className="w-full text-left">
                <thead className="sticky top-0 bg-[#1a1a1b] z-10">
                  <tr>
                    {["Date", "Close", "Volume", "Returns", "Vol10D", "VolChg", "PctRange", "RSI", "MACD", "VWAP", "HSIVol"].map((h, i) => (
                      <th key={i} className="px-2 py-1.5 text-[9px] text-zinc-600 uppercase tracking-wide font-medium whitespace-nowrap">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[...priceDfDict].reverse().map((row, idx) => (
                    <tr key={idx} className="border-t border-white/[0.04] hover:bg-white/[0.02]">
                      <td className="px-2 py-1.5 text-[10px] text-zinc-500 whitespace-nowrap">{priceDates[priceDfDict.length - 1 - idx] ?? ""}</td>
                      <td className="px-2 py-1.5 text-[10px] text-zinc-200 font-mono whitespace-nowrap">${(row.close ?? 0).toFixed(2)}</td>
                      <td className="px-2 py-1.5 text-[10px] text-zinc-400 font-mono whitespace-nowrap">{(row.Volume ?? 0).toLocaleString()}</td>
                      <td className={`px-2 py-1.5 text-[10px] font-mono whitespace-nowrap ${(row.returns ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                        {((row.returns ?? 0) * 100).toFixed(2)}%
                      </td>
                      <td className="px-2 py-1.5 text-[10px] text-zinc-400 font-mono whitespace-nowrap">{(row.volatility_10d ?? 0).toFixed(4)}</td>
                      <td className={`px-2 py-1.5 text-[10px] font-mono whitespace-nowrap ${(row.volume_change ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                        {((row.volume_change ?? 0) * 100).toFixed(2)}%
                      </td>
                      <td className="px-2 py-1.5 text-[10px] text-zinc-400 font-mono whitespace-nowrap">{(row.price_range ?? 0).toFixed(4)}</td>
                      <td className={`px-2 py-1.5 text-[10px] font-mono whitespace-nowrap ${(row.RSI ?? 50) > 70 ? "text-red-400" : (row.RSI ?? 50) < 30 ? "text-green-400" : "text-zinc-300"}`}>
                        {(row.RSI ?? 0).toFixed(1)}
                      </td>
                      <td className={`px-2 py-1.5 text-[10px] font-mono whitespace-nowrap ${(row.MACD ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                        {(row.MACD ?? 0).toFixed(4)}
                      </td>
                      <td className="px-2 py-1.5 text-[10px] text-zinc-400 font-mono whitespace-nowrap">{(row.vwap ?? 0).toFixed(2)}</td>
                      <td className="px-2 py-1.5 text-[10px] text-zinc-400 font-mono whitespace-nowrap">{(row.hsi_volatility ?? 0).toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Daily Sentiment */}
        <div className="px-4 py-3 border-b border-white/[0.06]">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-semibold text-zinc-300">Daily Sentiment</h3>
            {Object.keys(dailySentiment).length > 7 && (
              <button
                onClick={() => setSentimentExpanded((e) => !e)}
                className="text-[10px] text-blue-400 hover:text-blue-300"
              >
                {sentimentExpanded ? "Show less" : `Show all (${Object.keys(dailySentiment).length} days)`}
              </button>
            )}
          </div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[9px] text-zinc-600 w-20 flex-shrink-0">Date</span>
            <div className="flex-1 flex items-center">
              <div className="flex-1 relative h-3 rounded-full">
                <div className="absolute left-1/2 w-px h-full bg-white/10" />
              </div>
            </div>
            <span className="text-[10px] text-zinc-600 w-6 text-right">N</span>
          </div>
          <div className="space-y-1.5">
            {sortedDays.map(([date, vals]) => (
              <DailySentimentBar
                key={date}
                date={date}
                sentimentMean={vals.sentimentMean}
                newsCount={vals.newsCount}
              />
            ))}
          </div>
        </div>

        {/* News Items */}
        <div className="px-4 py-3">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-semibold text-zinc-300">
              News Headlines ({newsItems.length})
            </h3>
            {newsItems.length > 1 && (
              <button
                onClick={() => setNewsExpanded((e) => !e)}
                className="text-[10px] text-blue-400 hover:text-blue-300"
              >
                {newsExpanded ? "Collapse all" : "Expand all"}
              </button>
            )}
          </div>
          <div className="space-y-2">
            {newsItems.slice(0, newsExpanded ? undefined : 5).map((item, idx) => (
              <NewsItemCard key={idx} item={item} />
            ))}
            {!newsExpanded && newsItems.length > 5 && (
              <button
                onClick={() => setNewsExpanded(true)}
                className="w-full rounded-xl border border-dashed border-white/[0.1] p-2 text-[11px] text-zinc-500 hover:border-white/[0.2] hover:text-zinc-400 transition-colors"
              >
                Show {newsItems.length - 5} more headlines...
              </button>
            )}
          </div>
        </div>

        {/* Metadata */}
        {metadata && Object.keys(metadata).length > 0 && (
          <div className="px-4 pb-4">
            <h3 className="text-xs font-semibold text-zinc-600 mb-2">Pipeline Info</h3>
            <div className="rounded-xl border border-white/[0.04] bg-white/[0.02] p-3">
              <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                <div className="flex justify-between">
                  <span className="text-[10px] text-zinc-500">News Scraped</span>
                  <span className="text-[10px] text-zinc-300 font-mono">{String(metadata.news_scraped ?? metadata["news_scraped"] ?? "—")}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[10px] text-zinc-500">Headlines Labeled</span>
                  <span className="text-[10px] text-zinc-300 font-mono">{String(metadata.headlines_labeled ?? metadata["headlines_labeled"] ?? "—")}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[10px] text-zinc-500">Daily Rows</span>
                  <span className="text-[10px] text-zinc-300 font-mono">{String(metadata.daily_rows ?? metadata["daily_rows"] ?? "—")}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[10px] text-zinc-500">Price Rows</span>
                  <span className="text-[10px] text-zinc-300 font-mono">{String(metadata.price_rows ?? metadata["price_rows"] ?? "—")}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[10px] text-zinc-500">Lookback</span>
                  <span className="text-[10px] text-zinc-300 font-mono">{String(metadata.lookback_days ?? metadata["lookback_days"] ?? "—")} days</span>
                </div>
                {!!metadata.pipeline_start && (
                  <div className="flex justify-between col-span-2">
                    <span className="text-[10px] text-zinc-500">Started</span>
                    <span className="text-[10px] text-zinc-400 font-mono">{String(metadata.pipeline_start as string).split("T")[0]}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
