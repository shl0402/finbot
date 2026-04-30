// frontend/src/components/SectorDashboard.tsx
"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { createPortal } from "react-dom";
import { X, ExternalLink, Info, RotateCcw, ChevronLeft } from "lucide-react";
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import type { SectorPayload, SectorItem } from "@/types/chat";

interface SectorDashboardProps {
  payload: SectorPayload;
  onClose: () => void;
}

const SOURCE_LABELS: Record<SectorPayload["source"], string> = {
  tradingview: "TradingView",
  futunn: "Futunn",
  yfinance: "Yahoo Finance",
};

function parsePercent(s: string): number {
  if (!s || s === "N/A") return NaN;
  const cleaned = String(s).replace(/%/g, "").replace(/\+/g, "").replace(/\u2212/g, "-").replace(/−/g, "-").trim();
  const n = parseFloat(cleaned);
  return isNaN(n) ? NaN : n;
}

function parseMarketCap(s: string): number {
  if (!s || s === "N/A") return 0;
  const cleaned = s.replace(/[$,]/g, "").trim().toUpperCase();
  const match = cleaned.match(/^([\d.]+)(T|B|M|K)?/);
  if (!match) return 0;
  let val = parseFloat(match[1]);
  if (cleaned.includes("T")) val *= 1e12;
  else if (cleaned.includes("B")) val *= 1e9;
  else if (cleaned.includes("M")) val *= 1e6;
  else if (cleaned.includes("K")) val *= 1e3;
  return val;
}

function sectorColor(pct: number): { bg: string; bgHover: string; text: string; border: string } {
  if (isNaN(pct)) return { bg: "#27272a", bgHover: "#3f3f46", text: "#a1a1aa", border: "#3f3f46" };
  if (pct >= 3)   return { bg: "#16a34a", bgHover: "#22c55e", text: "#ffffff", border: "#22c55e" };
  if (pct >= 1.5) return { bg: "#22c55e", bgHover: "#4ade80", text: "#ffffff", border: "#4ade80" };
  if (pct >= 0.5) return { bg: "#4ade80cc", bgHover: "#4ade80e6", text: "#ffffff", border: "#4ade80" };
  if (pct >= 0)   return { bg: "#bbf7d0", bgHover: "#86efac", text: "#166534", border: "#86efac" };
  if (pct > -0.5) return { bg: "#fecaca", bgHover: "#fca5a5", text: "#7f1d1d", border: "#fca5a5" };
  if (pct > -1.5) return { bg: "#f87171cc", bgHover: "#f87171e6", text: "#ffffff", border: "#f87171" };
  if (pct > -3)   return { bg: "#ef4444", bgHover: "#dc2626", text: "#ffffff", border: "#f87171" };
  return { bg: "#dc2626", bgHover: "#b91c1c", text: "#ffffff", border: "#ef4444" };
}

const PERF_FIELDS = [
  { key: "perf1w" as const, label: "1W" },
  { key: "perf1m" as const, label: "1M" },
  { key: "perf3m" as const, label: "3M" },
  { key: "perf6m" as const, label: "6M" },
  { key: "perfYtd" as const, label: "YTD" },
  { key: "perf1y" as const, label: "1Y" },
  { key: "perf5y" as const, label: "5Y" },
  { key: "perf10y" as const, label: "10Y" },
  { key: "perfAllTime" as const, label: "All" },
];

const PIE_COLORS = [
  "#EF476F", // Vibrant Red/Pink
  "#F78C6B", // Soft Orange
  "#FFD166", // Bright Yellow
  "#06D6A0", // Emerald Green
  "#118AB2", // Deep Teal
  "#073B4C", // Dark Navy
  "#6A4C93", // Rich Purple
  "#F15BB5", // Magenta
  "#9D4EDD", // Bright Violet
  "#48CAE4"  // Sky Blue
];

function SectorTooltip({ sector, source }: { sector: SectorItem; source: SectorPayload["source"] }) {
  const availablePerf = PERF_FIELDS.filter((f) => {
    const val = sector[f.key as keyof SectorItem];
    return val != null && val !== "";
  });

  return (
    <div className="space-y-2 min-w-[180px]">
      <p className="text-sm font-semibold text-zinc-100 leading-tight">{sector.sector}</p>

      <div className="flex items-baseline gap-1.5">
        <span className={`text-lg font-bold ${
          (() => {
            const v = parsePercent(sector.changePercent);
            if (isNaN(v)) return "text-zinc-400";
            return v >= 0 ? "text-green-400" : "text-red-400";
          })()
        }`}>
          {sector.changePercent}
        </span>
        <span className="text-[10px] text-zinc-500">change</span>
      </div>

      {source === "tradingview" && (
        <div className="space-y-1 border-t border-white/10 pt-2">
          {sector.marketCap && (
            <div className="flex justify-between text-[11px]">
              <span className="text-zinc-500">Market Cap</span>
              <span className="text-zinc-300">{sector.marketCap}</span>
            </div>
          )}
          {sector.dividendYield && (
            <div className="flex justify-between text-[11px]">
              <span className="text-zinc-500">Div Yield</span>
              <span className="text-zinc-300">{sector.dividendYield}</span>
            </div>
          )}
          {sector.volume && (
            <div className="flex justify-between text-[11px]">
              <span className="text-zinc-500">Volume</span>
              <span className="text-zinc-300">{sector.volume}</span>
            </div>
          )}
          {sector.stocksCount && (
            <div className="flex justify-between text-[11px]">
              <span className="text-zinc-500">Stocks</span>
              <span className="text-zinc-300">{sector.stocksCount}</span>
            </div>
          )}

          {availablePerf.length > 0 && (
            <div className="border-t border-white/10 pt-1.5">
              <p className="mb-1 text-[10px] text-zinc-600 uppercase tracking-wide">Performance</p>
              <div className="flex flex-wrap gap-x-2">
                {PERF_FIELDS.map((f) => {
                  const val = sector[f.key as keyof SectorItem] as string | undefined;
                  if (!val) return null;
                  const pct = parsePercent(val);
                  const colorClass = isNaN(pct) ? "text-zinc-400" : pct >= 0 ? "text-green-400" : "text-red-400";
                  return (
                    <div key={f.key} className="flex items-baseline gap-1 flex-shrink-0">
                      <span className="text-[9px] text-zinc-600 whitespace-nowrap">{f.label}</span>
                      <span className={`text-[10px] font-medium ${colorClass} max-w-[4rem] truncate`}>
                        {val}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="border-t border-white/10 pt-1.5">
        <p className="text-[9px] text-zinc-600 italic">Click card to see performance chart</p>
      </div>

      {sector.link && sector.link !== "N/A" && (
        <a
          href={sector.link}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-[10px] text-blue-400 hover:text-blue-300 transition-colors"
        >
          View on {SOURCE_LABELS[source]} <ExternalLink size={8} />
        </a>
      )}
    </div>
  );
}

function SectorBack({ sector, onBack }: { sector: SectorItem; onBack: () => void }) {
  const chartData = PERF_FIELDS.filter((f) => {
    const val = sector[f.key as keyof SectorItem];
    return val != null && val !== "";
  }).map((f) => {
    const raw = sector[f.key as keyof SectorItem] as string;
    const pct = parsePercent(raw);
    return { name: f.label, value: isNaN(pct) ? 0 : pct };
  });

  if (chartData.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3">
        <p className="text-xs text-zinc-500 text-center px-4">No performance data available for this sector</p>
        <button
          onClick={onBack}
          className="flex items-center gap-1 rounded-full bg-white/10 px-3 py-1 text-xs text-zinc-400 hover:bg-white/20 hover:text-zinc-200 transition-colors"
        >
          <ChevronLeft size={10} /> Back
        </button>
      </div>
    );
  }

  const pct = parsePercent(sector.changePercent);
  const changeColor = isNaN(pct) ? "#a1a1aa" : pct >= 0 ? "#22c55e" : "#ef4444";

  return (
    <div className="flex flex-col h-full p-2">
      <div className="flex items-center justify-between mb-1 flex-shrink-0">
        <div className="flex items-center gap-1.5 min-w-0">
          <button
            onClick={onBack}
            className="flex items-center gap-0.5 rounded-full bg-white/10 px-2 py-0.5 text-[10px] text-zinc-400 hover:bg-white/20 hover:text-zinc-200 transition-colors flex-shrink-0"
          >
            <ChevronLeft size={9} /> Back
          </button>
          <p className="text-[10px] font-semibold text-zinc-100 truncate">{sector.sector}</p>
        </div>
        <span className="text-xs font-bold flex-shrink-0" style={{ color: changeColor }}>
          {sector.changePercent}
        </span>
      </div>

      <p className="text-[9px] text-zinc-600 mb-1 text-center flex-shrink-0">Performance across timeframes</p>

      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={chartData}
            margin={{ top: 2, right: 4, left: -18, bottom: 2 }}
          >
            <XAxis
              dataKey="name"
              tick={{ fontSize: 8, fill: "#71717a" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 8, fill: "#71717a" }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => `${v}%`}
            />
            <RechartsTooltip
              // 1. Fix the bright hover highlight behind the bar
              cursor={{ fill: "rgba(255, 255, 255, 0.06)" }} 
              
              formatter={(value: number) => [`${value.toFixed(2)}%`, "Change"]}
              contentStyle={{
                backgroundColor: "#1e1f20",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: "8px",
                fontSize: "10px",
                // 2. Brighten the default text color
                color: "#e4e4e7", 
              }}
              labelStyle={{ 
                // 3. Brighten the label text (e.g., "6M")
                color: "#a1a1aa", 
                fontSize: "10px",
                marginBottom: "2px"
              }}
              // 4. Force the item text (e.g., "Change : 28.61%") to be pale/white
              itemStyle={{ 
                color: "#f4f4f5" 
              }}
            />
            <Bar
              dataKey="value"
              radius={[3, 3, 0, 0]}
              maxBarSize={28}
            >
              {chartData.map((entry, index) => {
                const isPos = entry.value >= 0;
                return (
                  <Cell
                    key={`cell-${index}`}
                    fill={isPos ? "#22c55e" : "#ef4444"}
                    fillOpacity={0.85 + index * 0.015}
                  />
                );
              })}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default function SectorDashboard({ payload, onClose }: SectorDashboardProps) {
  const { sectors, source, interactive } = payload;
  const containerRef = useRef<HTMLDivElement>(null);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const hoveredSectorRef = useRef<SectorItem | null>(null);
  const tooltipHoverRef = useRef(false);
  const [tooltipAnchor, setTooltipAnchor] = useState<{ sector: SectorItem; rect: DOMRect } | null>(null);
  const [flippedSectorId, setFlippedSectorId] = useState<string | null>(null);

  useEffect(() => {
    const cancel = () => {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
      setTooltipAnchor(null);
      hoveredSectorRef.current = null;
    };
    window.addEventListener("scroll", cancel, true);
    window.addEventListener("resize", cancel, true);
    return () => {
      window.removeEventListener("scroll", cancel, true);
      window.removeEventListener("resize", cancel, true);
    };
  }, []);

  const sortedSectors = [...sectors].sort(
    (a, b) => parsePercent(b.changePercent) - parsePercent(a.changePercent)
  );

  const showTooltip = useCallback((sector: SectorItem, rect: DOMRect) => {
    if (flippedSectorId) return;
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    hoveredSectorRef.current = sector;
    tooltipHoverRef.current = false;
    setTooltipAnchor({ sector, rect });
  }, [flippedSectorId]);

  const scheduleHide = useCallback(() => {
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    hideTimerRef.current = setTimeout(() => {
      if (!tooltipHoverRef.current) {
        setTooltipAnchor(null);
        hoveredSectorRef.current = null;
      }
    }, 150);
  }, []);

  const handleCardClick = useCallback((sector: SectorItem) => {
    if (!interactive) return;
    if (flippedSectorId === sector.sector) {
      setFlippedSectorId(null);
    } else {
      setFlippedSectorId(sector.sector);
      setTooltipAnchor(null);
    }
  }, [interactive, flippedSectorId]);

  const handleBack = useCallback(() => {
    setFlippedSectorId(null);
  }, []);

  // ── Pie chart data ──────────────────────────────────────────────────────────
  const sectorsWithCap = sectors
    .filter((s) => s.marketCap && s.marketCap !== "N/A")
    .map((s) => ({ ...s, _capVal: parseMarketCap(s.marketCap!) }))
    .filter((s) => s._capVal > 0)
    .sort((a, b) => b._capVal - a._capVal);

  const topCapSectors = sectorsWithCap.slice(0, 8);
  const otherCap = sectorsWithCap.slice(8).reduce((sum, s) => sum + s._capVal, 0);
  const pieData = otherCap > 0
    ? [...topCapSectors, { sector: "Others", _capVal: otherCap, marketCap: "" }]
    : topCapSectors;

  const totalCap = pieData.reduce((sum, s) => sum + s._capVal, 0);

  function formatCapLabel(val: number): string {
    if (val >= 1e12) return `$${(val / 1e12).toFixed(1)}T`;
    if (val >= 1e9) return `$${(val / 1e9).toFixed(0)}B`;
    if (val >= 1e6) return `$${(val / 1e6).toFixed(0)}M`;
    return `$${val}`;
  }

  // ── Portal tooltip ──────────────────────────────────────────────────────────
  const TOOLTIP_WIDTH = 220;
  const TOOLTIP_GAP = 8;

  let tooltipEl: React.ReactNode = null;
  if (tooltipAnchor) {
    const { sector, rect } = tooltipAnchor;
    const flipLeft = typeof window !== "undefined" && window.innerWidth - rect.right < TOOLTIP_WIDTH + TOOLTIP_GAP;
    const left = flipLeft ? rect.left - TOOLTIP_WIDTH + 2 : rect.right - 2;
    const top = Math.min(rect.top, typeof window !== "undefined" ? window.innerHeight - 340 : rect.top);
    tooltipEl = createPortal(
      <div
        className="fixed z-[9999] max-w-[220px] rounded-xl border border-white/20 bg-[#1e1f20] p-3 shadow-2xl pointer-events-auto"
        style={{ left: `${left}px`, top: `${top}px` }}
        onMouseEnter={() => { tooltipHoverRef.current = true; }}
        onMouseLeave={() => {
          tooltipHoverRef.current = false;
          if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
          hideTimerRef.current = setTimeout(() => {
            setTooltipAnchor(null);
            hoveredSectorRef.current = null;
          }, 150);
        }}
      >
        <SectorTooltip sector={sector} source={source} />
      </div>,
      document.body
    );
  }

  const flippedSector = flippedSectorId
    ? sectors.find((s) => s.sector === flippedSectorId)
    : null;

  return (
    <div className="flex flex-shrink-0 flex-col border-l border-white/[0.08] bg-[#131314] h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.08] px-4 py-3 flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className="flex h-5 w-5 items-center justify-center rounded bg-gradient-to-br from-green-400 to-red-500">
            <div className="h-2.5 w-2.5 rounded-sm bg-white/80" />
          </div>
          <div>
            <p className="text-sm font-medium text-zinc-100">Sector Heatmap</p>
            <p className="text-[11px] text-zinc-500">{sectors.length} sectors</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="rounded-full p-1 text-zinc-500 transition-colors hover:bg-white/10 hover:text-zinc-200"
        >
          <X size={14} />
        </button>
      </div>

      {/* Source badge */}
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-2 flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="rounded bg-white/10 px-2 py-0.5 text-[10px] text-zinc-400">
            Source: {SOURCE_LABELS[source]}
          </span>
          {interactive && (
            <span className="flex items-center gap-1 rounded bg-blue-400/15 px-2 py-0.5 text-[10px] text-blue-400">
              <Info size={8} />
              Interactive
            </span>
          )}
          {!interactive && (
            <span className="rounded bg-amber-400/15 px-2 py-0.5 text-[10px] text-amber-400">
              Limited data
            </span>
          )}
        </div>
      </div>

      {/* Scrollable content */}
      <div ref={containerRef} className="flex-1 overflow-y-auto min-h-0">
        <div className="p-3">
          {/* Flipped / enlarged card */}
          {flippedSector ? (
            <div className="mb-3 rounded-xl border border-white/20 bg-[#1a1a1b] overflow-hidden"
              style={{ height: "180px", perspective: "800px" }}>
              <SectorBack sector={flippedSector} onBack={handleBack} />
            </div>
          ) : null}

          {/* Heatmap grid */}
          <div className="grid grid-cols-3 gap-1.5">
            {sortedSectors.map((sector, idx) => {
              const pct = parsePercent(sector.changePercent);
              const colors = sectorColor(pct);
              const isHovered = hoveredSectorRef.current === sector;
              const isFlipped = flippedSectorId === sector.sector;

              return (
                <div
                  key={idx}
                  className="relative cursor-pointer rounded-lg p-2 transition-all duration-200"
                  style={{
                    minHeight: "56px",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "center",
                    backgroundColor: isFlipped ? colors.bgHover : (isHovered ? colors.bgHover : colors.bg),
                    border: `1px solid ${colors.border}`,
                    transform: isHovered && !isFlipped ? "scale(1.04)" : "scale(1)",
                    zIndex: isHovered ? 10 : 1,
                    boxShadow: isFlipped ? "0 0 0 2px #6366f1, 0 4px 16px rgba(0,0,0,0.4)" : "none",
                  }}
                  onMouseEnter={(e) => {
                    if (!interactive || isFlipped) return;
                    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                    showTooltip(sector, rect);
                  }}
                  onMouseLeave={() => {
                    if (!interactive || isFlipped) return;
                    scheduleHide();
                  }}
                  onClick={() => handleCardClick(sector)}
                >
                  {isFlipped && (
                    <div className="absolute -top-px -right-px rounded-bl-lg rounded-tr-lg bg-indigo-500 px-1 py-0.5">
                      <RotateCcw size={7} className="text-white" />
                    </div>
                  )}
                  <p className="text-[10px] font-medium leading-tight" style={{ color: colors.text }}>
                    {sector.sector}
                  </p>
                  <p className="mt-0.5 text-sm font-bold" style={{ color: colors.text }}>
                    {sector.changePercent}
                  </p>
                  {interactive && !isFlipped && (
                    <p className="text-[8px] mt-0.5" style={{ color: colors.text, opacity: 0.6 }}>
                      click for chart
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          {/* Legend */}
          <div className="mt-4 flex items-center justify-center gap-3">
            <div className="flex items-center gap-1">
              <div className="h-2 w-4 rounded-sm bg-green-500" />
              <span className="text-[10px] text-zinc-500">Positive</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="h-2 w-4 rounded-sm bg-red-500" />
              <span className="text-[10px] text-zinc-500">Negative</span>
            </div>
            {interactive ? (
              <span className="text-[10px] text-zinc-600">Hover to preview · Click to chart</span>
            ) : (
              <span className="text-[10px] text-zinc-600">Fallback source — limited data</span>
            )}
          </div>

          {/* Pie chart — Market Cap Distribution */}
          {pieData.length > 1 && (
            <div className="mt-5 pt-4 border-t border-white/[0.06]">
              <div className="flex items-center justify-between mb-2">
                <p className="text-[11px] font-medium text-zinc-100">Market Cap Distribution</p>
                <span className="text-[9px] text-zinc-600">Top {pieData.length - (otherCap > 0 ? 1 : 0)} sectors</span>
              </div>
              <div className="flex items-center gap-3">
                <div style={{ width: 120, height: 120 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={pieData}
                        dataKey="_capVal"
                        nameKey="sector"
                        cx="50%"
                        cy="50%"
                        innerRadius={28}
                        outerRadius={52}
                        strokeWidth={0}
                        paddingAngle={1}
                      >
                        {pieData.map((_, index) => (
                          <Cell key={`pie-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <RechartsTooltip
                      formatter={(value: number, name: string) => [
                        formatCapLabel(value),
                        name,
                      ]}
                      contentStyle={{
                        backgroundColor: "#1e1f20",
                        border: "1px solid rgba(255,255,255,0.1)",
                        borderRadius: "8px",
                        fontSize: "10px",
                        color: "#f4f4f5", // <-- Updated to a pale white
                      }}
                      itemStyle={{ 
                        color: "#f4f4f5"  // <-- ADDED: Forces the sector name and value to be pale white
                      }}
                      labelStyle={{ 
                        color: "#a1a1aa", // <-- Lightened slightly to a visible gray
                        fontSize: "9px" 
                      }}
                    />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="flex flex-col gap-1 min-w-0 flex-1">
                  {pieData.map((s, i) => { 
                    const pct = totalCap > 0 ? (s._capVal / totalCap * 100) : 0;
                    return (
                      <div key={i} className="flex items-center gap-1.5 min-w-0">
                        <div
                          className="w-2 h-2 rounded-full flex-shrink-0"
                          style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }}
                        />
                        <span className="text-[9px] text-zinc-400 truncate flex-shrink-0" style={{ maxWidth: "70px" }}>
                          {s.sector}
                        </span>
                        <div className="flex-1 min-w-0 bg-white/5 rounded-full h-1">
                          <div
                            className="h-1 rounded-full"
                            style={{ width: `${pct}%`, backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }}
                          />
                        </div>
                        <span className="text-[9px] text-zinc-500 flex-shrink-0 w-8 text-right">
                          {pct.toFixed(0)}%
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Portal tooltip */}
      {tooltipEl}
    </div>
  );
}
