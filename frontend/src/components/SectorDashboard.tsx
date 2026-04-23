// frontend/src/components/SectorDashboard.tsx
"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { createPortal } from "react-dom";
import { X, ExternalLink, Info } from "lucide-react";
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

interface TooltipState {
  sector: SectorItem;
  viewportX: number;
  viewportY: number;
  targetRect: DOMRect;
}

function SectorTooltip({ sector, source }: { sector: SectorItem; source: SectorPayload["source"] }) {
  const perfFields = [
    { key: "perf1w", label: "1W" },
    { key: "perf1m", label: "1M" },
    { key: "perf3m", label: "3M" },
    { key: "perf6m", label: "6M" },
    { key: "perfYtd", label: "YTD" },
    { key: "perf1y", label: "1Y" },
    { key: "perf5y", label: "5Y" },
    { key: "perf10y", label: "10Y" },
    { key: "perfAllTime", label: "All Time" },
  ];

  const availablePerf = perfFields.filter((f) => {
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

      {/* Extended info only for TradingView */}
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
          {sector.industriesCount && (
            <div className="flex justify-between text-[11px]">
              <span className="text-zinc-500">Industries</span>
              <span className="text-zinc-300">{sector.industriesCount}</span>
            </div>
          )}
          {sector.stocksCount && (
            <div className="flex justify-between text-[11px]">
              <span className="text-zinc-500">Stocks</span>
              <span className="text-zinc-300">{sector.stocksCount}</span>
            </div>
          )}

          {availablePerf.length > 0 && (
            <>
              <div className="border-t border-white/10 pt-1.5">
                <p className="mb-1 text-[10px] text-zinc-600 uppercase tracking-wide">Performance</p>
                <div className="flex flex-wrap gap-x-2">
                  {perfFields.map((f) => {
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
            </>
          )}
        </div>
      )}

      {/* Non-interactive: show a hint */}
      {!source && (
        <p className="text-[10px] text-zinc-600 italic">Hover for details</p>
      )}

      {/* Link */}
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

export default function SectorDashboard({ payload, onClose }: SectorDashboardProps) {
  const { sectors, source, interactive } = payload;
  const containerRef = useRef<HTMLDivElement>(null);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const hoveredSectorRef = useRef<SectorItem | null>(null);
  const hoveredRectRef = useRef<DOMRect | null>(null);
  const tooltipHoverRef = useRef(false);
  const [tooltipAnchor, setTooltipAnchor] = useState<{ sector: SectorItem; rect: DOMRect } | null>(null);

  useEffect(() => {
    const cancel = () => {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
      setTooltipAnchor(null);
      hoveredSectorRef.current = null;
      hoveredRectRef.current = null;
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

  const TOOLTIP_WIDTH = 220;
  const TOOLTIP_GAP = 8;

  const showTooltip = useCallback((sector: SectorItem, rect: DOMRect) => {
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    hoveredSectorRef.current = sector;
    hoveredRectRef.current = rect;
    tooltipHoverRef.current = false;
    setTooltipAnchor({ sector, rect });
  }, []);

  const scheduleHide = useCallback(() => {
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    hideTimerRef.current = setTimeout(() => {
      if (!tooltipHoverRef.current) {
        setTooltipAnchor(null);
        hoveredSectorRef.current = null;
        hoveredRectRef.current = null;
      }
    }, 150);
  }, []);

  let tooltipEl: React.ReactNode = null;
  if (tooltipAnchor) {
    const { sector, rect } = tooltipAnchor;
    const flipLeft = window.innerWidth - rect.right < TOOLTIP_WIDTH + TOOLTIP_GAP;
    const left = flipLeft ? rect.left - TOOLTIP_WIDTH + 2 : rect.right - 2;
    const top = Math.min(rect.top, window.innerHeight - 320);
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
            hoveredRectRef.current = null;
          }, 150);
        }}
      >
        <SectorTooltip sector={sector} source={source} />
      </div>,
      document.body
    );
  }

  return (
    <div className="flex flex-shrink-0 flex-col border-l border-white/[0.08] bg-[#131314] h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.08] px-4 py-3">
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
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-2">
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

      {/* Heatmap grid */}
      <div ref={containerRef} className="flex-1 overflow-y-auto p-3">
        <div className="grid grid-cols-3 gap-1.5">
          {sortedSectors.map((sector, idx) => {
            const pct = parsePercent(sector.changePercent);
            const colors = sectorColor(pct);
            const isHovered = hoveredSectorRef.current === sector;

            return (
              <div
                key={idx}
                className="relative cursor-pointer rounded-lg p-2 transition-all duration-150 hover:z-10"
                style={{
                  minHeight: "56px",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "center",
                  backgroundColor: isHovered ? colors.bgHover : colors.bg,
                  border: `1px solid ${colors.border}`,
                  transform: isHovered ? "scale(1.03)" : "scale(1)",
                  zIndex: isHovered ? 10 : 1,
                }}
                onMouseEnter={(e) => {
                  if (!interactive) return;
                  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                  showTooltip(sector, rect);
                }}
                onMouseLeave={() => {
                  if (!interactive) return;
                  scheduleHide();
                }}
              >
                <p className="text-[10px] font-medium leading-tight" style={{ color: colors.text }}>
                  {sector.sector}
                </p>
                <p className="mt-0.5 text-sm font-bold" style={{ color: colors.text }}>
                  {sector.changePercent}
                </p>
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
            <span className="text-[10px] text-zinc-600">Hover for details</span>
          ) : (
            <span className="text-[10px] text-zinc-600">Fallback source — limited data</span>
          )}
        </div>
      </div>

      {/* Portal tooltip — rendered to body to escape overflow clipping */}
      {tooltipEl}

    </div>
  );
}
