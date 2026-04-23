// frontend/src/components/ThinkingProcess.tsx
"use client";

import { useState } from "react";
import type { ThinkingStep, Phase, StepStatus } from "@/types/chat";
import { logger } from "@/lib/logger";

interface ThinkingProcessProps {
  steps: ThinkingStep[];
  isProcessing: boolean;
  maxHeight?: number;
  onHeightChange?: (height: number) => void;
}

const PHASE_LABELS: Record<Phase, string> = {
  intent_routing: "Intent Routing",
  tool_selection: "Tool Selection",
  tool_execution: "Tool Execution",
  response_generation: "Response Generation",
};

const PHASE_COLORS: Record<Phase, string> = {
  intent_routing: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  tool_selection: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  tool_execution: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  response_generation: "bg-green-500/20 text-green-400 border-green-500/30",
};

const PHASE_ICONS: Record<Phase, React.ReactNode> = {
  intent_routing: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 8v4l3 3" />
    </svg>
  ),
  tool_selection: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 2L2 7l10 5 10-5-10-5z" />
      <path d="M2 17l10 5 10-5" />
      <path d="M2 12l10 5 10-5" />
    </svg>
  ),
  tool_execution: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polygon points="5 3 19 12 5 21 5 3" />
    </svg>
  ),
  response_generation: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  ),
};

function StatusIcon({ status }: { status: StepStatus }) {
  if (status === "active") {
    return (
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        className="animate-spin text-blue-400"
        style={{ animationDuration: "1.5s" }}
      >
        <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
        <path d="M12 2a10 10 0 0 1 10 10" strokeOpacity="1" />
      </svg>
    );
  }
  if (status === "success") {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-green-400">
        <polyline points="20 6 9 17 4 12" />
      </svg>
    );
  }
  if (status === "failed") {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-red-400">
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    );
  }
  // skipped
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-zinc-500">
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

function ToolBadge({ tool }: { tool: string }) {
  const color = tool.includes("tradingview")
    ? "bg-tradingview/20 text-tradingview border-tradingview/30"
    : tool.includes("futunn")
    ? "bg-futunn/20 text-futunn border-futunn/30"
    : tool.includes("yfinance")
    ? "bg-yfinance/20 text-yfinance border-yfinance/30"
    : "bg-white/10 text-zinc-400 border-white/10";

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-mono ${color}`}
    >
      {tool}
    </span>
  );
}

export default function ThinkingProcess({ steps, isProcessing, maxHeight = 256, onHeightChange }: ThinkingProcessProps) {
  const [collapsed, setCollapsed] = useState(false);

  const hasCompletedSteps = steps.length > 0;

  // Auto-collapse when processing finishes and we have steps
  if (!isProcessing && hasCompletedSteps && !collapsed) {
    // Show a small summary button instead
  }

  if (!hasCompletedSteps && !isProcessing) {
    return null;
  }

  return (
    <div className="flex flex-col border-t border-white/[0.06] bg-[#0f0f10]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#a8c7fa" strokeWidth="2" className="animate-pulse">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
          <span className="text-xs font-medium text-zinc-300">Thinking Process</span>
          {hasCompletedSteps && (
            <span className="rounded-full bg-white/10 px-1.5 py-0.5 text-[10px] text-zinc-500">
              {steps.length} step{steps.length !== 1 ? "s" : ""}
            </span>
          )}
          {isProcessing && (
            <span className="flex h-2 w-2 rounded-full bg-blue-400">
              <span className="absolute inline-flex h-2 w-2 rounded-full bg-blue-400 opacity-75 animate-ping" />
            </span>
          )}
        </div>

        <button
          onClick={() => setCollapsed((c) => !c)}
          className="flex items-center gap-1 rounded px-2 py-1 text-xs text-zinc-500 transition-colors hover:bg-white/10 hover:text-zinc-300"
        >
          {collapsed ? (
            <>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="6 9 12 15 18 9" />
              </svg>
              Show
            </>
          ) : (
            <>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="18 15 12 9 6 15" />
              </svg>
              Hide
            </>
          )}
        </button>
      </div>

      {/* Steps list */}
      {!collapsed && (
        <>
          <div className="flex flex-col gap-0 overflow-y-auto px-4 py-3" style={{ maxHeight }}>
            {steps.map((step, idx) => {
            const isLast = idx === steps.length - 1;
            const phaseColor = PHASE_COLORS[step.phase] ?? "bg-white/10 text-zinc-400";
            const phaseLabel = PHASE_LABELS[step.phase] ?? step.phase;
            const phaseIcon = PHASE_ICONS[step.phase];

            return (
              <div key={idx} className="flex items-start gap-3 py-1.5">
                {/* Timeline line */}
                {idx > 0 && (
                  <div className="absolute left-[28px] top-0 h-1.5 w-px bg-white/[0.06]" style={{ top: "-8px" }} />
                )}

                {/* Step number + icon */}
                <div className="relative flex flex-shrink-0 flex-col items-center gap-1">
                  <div
                    className={`flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full border ${phaseColor}`}
                  >
                    {phaseIcon}
                  </div>
                </div>

                {/* Content */}
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] font-medium text-zinc-500">
                      #{step.stepNumber}
                    </span>
                    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${phaseColor}`}>
                      {phaseLabel}
                    </span>
                    {step.toolUsed && <ToolBadge tool={step.toolUsed} />}
                    <div className="ml-auto flex items-center gap-1">
                      <StatusIcon status={step.status} />
                    </div>
                  </div>

                  <p className="text-xs leading-relaxed text-zinc-300">{step.content}</p>

                  {step.toolResultPreview && (
                    <details className="mt-1 rounded border border-white/[0.06] bg-black/20">
                      <summary className="cursor-pointer px-2 py-1 text-[10px] text-zinc-600 hover:text-zinc-400">
                        Tool result preview
                      </summary>
                      <pre className="overflow-x-auto px-2 py-2 text-[10px] text-zinc-500 font-mono whitespace-pre-wrap break-all">
                        {step.toolResultPreview}
                      </pre>
                    </details>
                  )}
                </div>
              </div>
            );
          })}

          {/* Active step indicator */}
          {isProcessing && steps.length > 0 && steps[steps.length - 1].status === "active" && (
            <div className="ml-10 mt-1 flex items-center gap-2">
              <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-400" />
              <span className="text-[11px] text-blue-400/70 animate-pulse">
                {steps[steps.length - 1].content}
              </span>
            </div>
          )}
        </div>

        {/* Resize handle */}
        <div
          className="group h-2 cursor-ns-resize flex-shrink-0 flex items-center justify-center"
          onMouseDown={(e) => {
            e.preventDefault();
            const startY = e.clientY;
            const startH = maxHeight;
            function onMove(me: MouseEvent) {
              const delta = me.clientY - startY;
              const newH = Math.max(80, Math.min(500, startH + delta));
              onHeightChange?.(newH);
            }
            function onUp() {
              window.removeEventListener("mousemove", onMove);
              window.removeEventListener("mouseup", onUp);
            }
            window.addEventListener("mousemove", onMove);
            window.addEventListener("mouseup", onUp);
          }}
          >
            <div className="h-0.5 w-8 rounded-full bg-white/[0.06] transition-colors group-hover:bg-blue-400/40" />
          </div>
        </>
      )} {/* <--- PROPERLY CLOSED */}

      {/* Collapsed summary */}
      {collapsed && hasCompletedSteps && (
        <div className="px-4 py-2">
          <div className="flex flex-wrap gap-1">
            {steps.map((step, idx) => (
              <div key={idx} className="flex items-center gap-1">
                <StatusIcon status={step.status} />
                <span className="text-[10px] text-zinc-500">{PHASE_LABELS[step.phase]}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
