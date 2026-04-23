// frontend/src/components/CompanyDashboard.tsx
"use client";

import { X, TrendingUp, ExternalLink } from "lucide-react";
import type { CompanyInfoPayload, MetricCard } from "@/types/chat";
import { logger } from "@/lib/logger";

interface CompanyDashboardProps {
  payload: CompanyInfoPayload;
  onClose: () => void;
}

function MetricCardItem({ card }: { card: MetricCard }) {
  const isPositive = card.deltaColor === "normal";
  const isNegative = card.deltaColor === "inverse";

  return (
    <div className="rounded-xl border border-white/[0.06] bg-[#1e1f20] p-3 transition-colors hover:border-white/[0.12]">
      <p className="mb-0.5 text-[10px] text-zinc-500 uppercase tracking-wide">{card.label}</p>
      <p className="text-sm font-semibold text-zinc-100">{card.value}</p>
      {card.delta && (
        <p className={`mt-0.5 text-[10px] ${isNegative ? "text-red-400" : isPositive ? "text-green-400" : "text-zinc-500"}`}>
          {card.delta}
        </p>
      )}
    </div>
  );
}

function isUrl(value: string): boolean {
  return /^https?:\/\//i.test(value.trim());
}

function ProfileRow({ label, value }: { label: string; value: string }) {
  if (!value || value === "N/A" || value === "n/a") return null;

  const isClickable = isUrl(value);

  return (
    <div className="flex items-start justify-between border-b border-white/[0.04] py-2">
      <span className="text-[11px] text-zinc-500">{label}</span>
      {isClickable ? (
        <a
          href={value}
          target="_blank"
          rel="noopener noreferrer"
          className="max-w-[55%] text-right text-[11px] text-blue-400 underline underline-offset-2 hover:text-blue-300"
        >
          {value.replace(/^https?:\/\//, "")}
        </a>
      ) : (
        <span className="max-w-[55%] text-right text-[11px] text-zinc-300">{value}</span>
      )}
    </div>
  );
}

export default function CompanyDashboard({ payload, onClose }: CompanyDashboardProps) {
  const {
    companyName,
    symbol,
    price,
    change,
    changePercent,
    marketCap,
    peRatio,
    description,
    stats,
    profile,
  } = payload;

  const changeVal = parseFloat(change.replace(/[^0-9.-]/g, "") || "0");
  const isPositive = changeVal >= 0;

  logger.debug("Rendering CompanyDashboard for:", companyName);

  return (
    <div className="flex flex-shrink-0 flex-col border-l border-white/[0.08] bg-[#131314] h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.08] px-4 py-3">
        <div className="flex items-center gap-2">
          <TrendingUp size={14} className="text-blue-400" />
          <div>
            <p className="text-sm font-medium text-zinc-100 leading-tight">{companyName}</p>
            <p className="text-[11px] text-zinc-500">{symbol || "—"}</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="rounded-full p-1 text-zinc-500 transition-colors hover:bg-white/10 hover:text-zinc-200"
        >
          <X size={14} />
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {/* Price ticker */}
        <div className="rounded-2xl border border-white/[0.08] bg-[#1e1f20] p-4">
          <div className="flex items-end justify-between">
            <div>
              <p className="text-[10px] text-zinc-500 uppercase tracking-wide">Current Price</p>
              <p className="mt-1 text-2xl font-bold text-zinc-100">{price || "—"}</p>
              {(change || changePercent) && (
                <p className={`mt-0.5 text-sm font-medium ${isPositive ? "text-green-400" : "text-red-400"}`}>
                  {isPositive ? "+" : ""}{change || ""} ({changePercent || ""})
                </p>
              )}
            </div>

            {/* Mini sparkline placeholder */}
            <div className="flex h-12 items-end gap-0.5">
              {[0.55, 0.6, 0.52, 0.65, 0.58, 0.7, isPositive ? 0.72 : 0.62, isPositive ? 0.68 : 0.58].map((h, i) => (
                <div
                  key={i}
                  className={`w-1.5 rounded-sm ${isPositive ? "bg-green-500/60" : "bg-red-500/60"}`}
                  style={{ height: `${h * 100}%` }}
                />
              ))}
            </div>
          </div>

          {/* Key quick stats */}
          <div className="mt-3 grid grid-cols-2 gap-2 border-t border-white/[0.06] pt-3">
            <div>
              <p className="text-[10px] text-zinc-500">Market Cap</p>
              <p className="text-xs font-medium text-zinc-200">{marketCap || "—"}</p>
            </div>
            <div>
              <p className="text-[10px] text-zinc-500">P/E Ratio</p>
              <p className="text-xs font-medium text-zinc-200">{peRatio || "—"}</p>
            </div>
          </div>
        </div>

        {/* Description */}
        {description && description !== "N/A" && (
          <div>
            <p className="mb-2 text-xs font-medium text-zinc-300">About</p>
            <p className="line-clamp-4 text-xs leading-relaxed text-zinc-400">{description}</p>
          </div>
        )}

        {/* Stats grid */}
        {stats && stats.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-medium text-zinc-300">Key Statistics</p>
            <div className="grid grid-cols-2 gap-2">
              {stats.map((card, i) => (
                <MetricCardItem key={i} card={card} />
              ))}
            </div>
          </div>
        )}

        {/* Profile section */}
        {profile && Object.keys(profile).length > 0 && (
          <div>
            <p className="mb-2 text-xs font-medium text-zinc-300">Company Profile</p>
            <div className="rounded-xl border border-white/[0.06] bg-[#1e1f20] px-3">
              <ProfileRow label="Sector" value={profile["Sector"] || profile["sector"] || ""} />
              <ProfileRow label="Industry" value={profile["Industry"] || profile["industry"] || ""} />
              <ProfileRow label="CEO" value={profile["CEO"] || profile["ceo"] || ""} />
              <ProfileRow label="Employees" value={profile["Employees"] || profile["employees"] || ""} />
              <ProfileRow label="IPO Date" value={profile["Listing Date"] || profile["ipo_date"] || ""} />
              <ProfileRow label="Website" value={profile["Website"] || profile["website"] || ""} />
              <ProfileRow label="Business" value={profile["Business"] || profile["business"] || ""} />
            </div>
          </div>
        )}

        {/* Source footer */}
        <div className="flex items-center justify-center gap-1.5 pt-2">
          <span className="text-[10px] text-zinc-600">Data from</span>
          <span className="flex items-center gap-1 text-[10px] text-futunn font-medium">
            Futunn
            <ExternalLink size={8} />
          </span>
        </div>
      </div>
    </div>
  );
}
