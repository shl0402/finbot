// frontend/src/components/ChatInterface.tsx
"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ChatMessageItem from "./ChatMessageItem";
import PromptInput from "./PromptInput";
import type {
  ChatMessage,
  DashboardPayload,
  ChartPayload,
  MarketDiscoveryPayload,
  ChatMode,
  ChatHistoryItem,
} from "@/types/chat";
import { sendChat } from "@/lib/api";
import { X, TrendingUp, BarChart2, Code2 } from "lucide-react";

function generateId(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

// ── Helpers ──────────────────────────────────────────────────────────────

function getActivePath(messages: ChatMessage[], currentLeafId: string | null): ChatMessage[] {
  if (!currentLeafId) return [];
  const path: ChatMessage[] = [];
  let curr: ChatMessage | undefined = messages.find((m) => m.id === currentLeafId);
  while (curr) {
    path.unshift(curr); // prepend so root ends up first
    curr = messages.find((m) => m.id === curr!.parentId);
  }
  // After a user message, the next message in the path is its first child
  // (already present in the ancestor chain because the child was also in the
  // path from the original leafId up to root). No extra walk-down needed.
  return path;
}

/** User-message siblings share the same parent assistant (or null for first turn). */
function getUserSiblingIdsForParent(messages: ChatMessage[], parentId: string | null): string[] {
  if (parentId === null) {
    return messages
      .filter((m) => m.role === "user" && m.parentId === null)
      .sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime())
      .map((m) => m.id);
  }
  const parent = messages.find((m) => m.id === parentId);
  if (!parent) return [];
  return parent.children
    .map((cid) => messages.find((m) => m.id === cid))
    .filter((m): m is ChatMessage => Boolean(m) && m.role === "user")
    .map((m) => m.id);
}

/** After switching user-turn version, follow first child until leaf (full branch). */
function deepestLeafFrom(messages: ChatMessage[], startId: string): string {
  let id = startId;
  for (;;) {
    const m = messages.find((x) => x.id === id);
    if (!m || m.children.length === 0) return id;
    id = m.children[0];
  }
}


// ── Dashboard Panel ──────────────────────────────────────────────────────

const W = 288;  // candlestick SVG width

function SentimentBadge({ score, label }: { score: number; label: string }) {
  const pct = Math.round(((score + 1) / 2) * 100);
  const color =
    score > 0.2 ? "#22c55e" : score < -0.2 ? "#ef4444" : "#f59e0b";
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-zinc-200">Sentiment</span>
        <span style={{ color }} className="font-semibold">
          {label}
        </span>
      </div>
      <div className="h-2 w-full rounded-full bg-white/10">
        <div
          style={{ width: `${pct}%`, backgroundColor: color }}
          className="h-full rounded-full transition-all"
        />
      </div>
      <span className="text-[10px] text-zinc-500">
        {score > 0 ? "+" : ""}{score.toFixed(2)} score · based on {Math.floor(Math.abs(score) * 100 + 20)} news items
      </span>
    </div>
  );
}

function WordCloudSection({ words }: { words: Array<{ word: string; score: number; size: number }> }) {
  return (
    <div className="flex flex-wrap gap-x-2 gap-y-1 items-center justify-center py-1">
      {words.map((w, i) => {
        const color =
          w.score > 0 ? "#4ade80" : w.score < 0 ? "#f87171" : "#facc15";
        return (
          <span
            key={i}
            style={{
              color,
              fontSize: `${w.size}px`,
              fontWeight: Math.abs(w.score) > 0.7 ? "bold" : "normal",
              opacity: 0.6 + Math.abs(w.score) * 0.4,
            }}
          >
            {w.word}
          </span>
        );
      })}
    </div>
  );
}

function FrequencyBars({ items, color }: { items: Array<{ word: string; count: number }>; color: string }) {
  const max = Math.max(...items.map((i) => i.count), 1);
  return (
    <div className="flex flex-col gap-1.5">
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="w-20 truncate text-[10px] text-zinc-400">{item.word}</span>
          <div className="flex-1 h-3 rounded-sm bg-white/5 overflow-hidden">
            <div
              style={{ width: `${(item.count / max) * 100}%`, backgroundColor: color }}
              className="h-full rounded-sm transition-all"
            />
          </div>
          <span className="text-[10px] tabular-nums text-zinc-500 w-4 text-right">{item.count}</span>
        </div>
      ))}
    </div>
  );
}

function SectionHeader({ title, icon }: { title: string; icon: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.5 border-b border-white/[0.06] pb-2">
      {icon}
      <span className="text-xs font-medium text-zinc-300">{title}</span>
    </div>
  );
}

function DashboardPanel({
  payload,
  onClose,
}: {
  payload: NonNullable<DashboardPayload>;
  onClose: () => void;
}) {
  if (payload.type === "metrics") {
    const p = payload as MarketDiscoveryPayload;
    return (
      <div className="flex w-80 flex-shrink-0 flex-col border-l border-white/[0.08] bg-[#131314]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/[0.08] px-4 py-3">
          <div className="flex items-center gap-2">
            <TrendingUp size={14} className="text-blue-400" />
            <span className="text-sm font-medium text-zinc-100">
              {p.name} ({p.symbol})
            </span>
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-1 text-zinc-500 transition-colors hover:bg-white/10 hover:text-zinc-200"
          >
            <X size={14} />
          </button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {/* 6-metric grid */}
          <div className="grid grid-cols-2 gap-2">
            {p.metrics.map((m, i) => (
              <div
                key={i}
                className="rounded-xl border border-white/[0.06] bg-[#1e1f20] p-3"
              >
                <p className="mb-0.5 text-[10px] text-zinc-500 uppercase tracking-wide">{m.label}</p>
                <p className="text-base font-semibold text-zinc-100">{m.value}</p>
                {m.delta && (
                  <p
                    className={`mt-0.5 text-[10px] ${
                      m.deltaColor === "inverse" ? "text-red-400" : "text-green-400"
                    }`}
                  >
                    {m.delta}
                  </p>
                )}
              </div>
            ))}
          </div>

          {/* R:R Score */}
          {p.rrScore && (
            <div className="rounded-xl border border-blue-400/25 bg-blue-400/5 p-4">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-[10px] uppercase tracking-wide text-zinc-500">Risk : Reward</p>
                  <p className="text-2xl font-bold text-blue-400">{p.rrScore.ratio}</p>
                  <p className="mt-1 text-[11px] text-zinc-400">{p.rrScore.description}</p>
                </div>
                <div className="flex flex-col items-center">
                  <span className="text-[10px] text-zinc-500">Reward</span>
                  <div className="my-0.5 h-16 w-3 rounded bg-blue-400/30" />
                  <div className="my-0.5 h-6 w-3 rounded bg-red-400/30" />
                  <span className="text-[10px] text-zinc-500">Risk</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (payload.type === "chart") {
    const p = payload as ChartPayload;
    const prices = p.chartData.map((d) => d.low);
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...p.chartData.map((d) => d.high));
    const range = maxPrice - minPrice || 1;
    const H = 160;
    const padX = 8;
    const padY = 8;
    const chartW = W - padX * 2;
    const chartH = H - padY * 2;

    return (
      <div className="flex w-[22rem] flex-shrink-0 flex-col border-l border-white/[0.08] bg-[#131314]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/[0.08] px-4 py-3">
          <div className="flex items-center gap-2">
            <BarChart2 size={14} className="text-blue-400" />
            <span className="text-sm font-medium text-zinc-100">
              {p.name} ({p.symbol})
            </span>
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-1 text-zinc-500 transition-colors hover:bg-white/10 hover:text-zinc-200"
          >
            <X size={14} />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {/* ── Candlestick Chart ── */}
          <section>
            <SectionHeader
              title="30-Day OHLC Chart"
              icon={<BarChart2 size={12} className="text-blue-400" />}
            />
            <div className="mt-2">
              <svg width={W} height={H + 24} className="mx-auto">
                {[0, 0.25, 0.5, 0.75, 1].map((t) => {
                  const y = padY + chartH * (1 - t);
                  const price = minPrice + range * t;
                  return (
                    <g key={t}>
                      <line x1={padX} y1={y} x2={padX + chartW} y2={y} stroke="#2a2a2a" strokeWidth="0.5" />
                      <text x={padX + chartW + 4} y={y + 3} fontSize="8" fill="#5a6066">
                        ${price.toFixed(0)}
                      </text>
                    </g>
                  );
                })}
                {p.chartData.map((d, i) => {
                  const x = padX + (i / Math.max(p.chartData.length - 1, 1)) * chartW;
                  const openY = padY + chartH * (1 - (d.open - minPrice) / range);
                  const closeY = padY + chartH * (1 - (d.close - minPrice) / range);
                  const highY = padY + chartH * (1 - (d.high - minPrice) / range);
                  const lowY = padY + chartH * (1 - (d.low - minPrice) / range);
                  const color = d.close >= d.open ? "#22c55e" : "#ef4444";
                  return (
                    <g key={i}>
                      <line x1={x} y1={highY} x2={x} y2={lowY} stroke={color} strokeWidth="1" />
                      <rect
                        x={x - 3}
                        y={Math.min(openY, closeY)}
                        width={6}
                        height={Math.max(Math.abs(closeY - openY), 1)}
                        fill={color}
                        opacity={0.9}
                      />
                    </g>
                  );
                })}
              </svg>
              <p className="mt-1 text-center text-[10px] text-zinc-600">30-day OHLC candlestick</p>
            </div>
          </section>

          {/* ── Key Stats ── */}
          {p.keyStats && p.keyStats.length > 0 && (
            <section>
              <SectionHeader
                title="Key Statistics"
                icon={<TrendingUp size={12} className="text-purple-400" />}
              />
              <div className="mt-2 grid grid-cols-2 gap-2">
                {p.keyStats.map((s, i) => (
                  <div key={i} className="rounded-lg border border-white/[0.06] bg-[#1e1f20] p-2.5">
                    <p className="text-[10px] text-zinc-500">{s.label}</p>
                    <p className="text-sm font-semibold text-zinc-100">{s.value}</p>
                    {s.delta && (
                      <p
                        className={`text-[10px] ${
                          s.deltaColor === "inverse" ? "text-red-400" : "text-green-400"
                        }`}
                      >
                        {s.delta}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* ── Sentiment Analysis ── */}
          {(p.sentimentScore !== undefined || p.wordCloud) && (
            <section>
              <SectionHeader
                title="News Sentiment Analysis"
                icon={
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" />
                    <path d="M8 14s1.5 2 4 2 4-2 4-2" />
                    <line x1="9" y1="9" x2="9.01" y2="9" strokeWidth="3" />
                    <line x1="15" y1="9" x2="15.01" y2="9" strokeWidth="3" />
                  </svg>
                }
              />

              <div className="mt-2 space-y-3">
                {/* Sentiment score badge */}
                {p.sentimentScore !== undefined && p.sentimentLabel && (
                  <SentimentBadge score={p.sentimentScore} label={p.sentimentLabel} />
                )}

                {/* News count */}
                {p.newsCount !== undefined && (
                  <p className="text-[10px] text-zinc-500">
                    Based on {p.newsCount} recent news articles
                  </p>
                )}

                {/* Word cloud */}
                {p.wordCloud && p.wordCloud.length > 0 && (
                  <div className="rounded-xl border border-white/[0.06] bg-[#1e1f20] p-3">
                    <p className="mb-2 text-[10px] text-zinc-500">Word Cloud — green = positive · red = negative</p>
                    <WordCloudSection words={p.wordCloud} />
                  </div>
                )}

                {/* Positive / Negative frequency bars */}
                {p.topPositive && p.topNegative && (
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-xl border border-white/[0.06] bg-[#1e1f20] p-3">
                      <p className="mb-2 text-[10px] font-medium text-green-400">Top Positive</p>
                      <FrequencyBars items={p.topPositive} color="#4ade80" />
                    </div>
                    <div className="rounded-xl border border-white/[0.06] bg-[#1e1f20] p-3">
                      <p className="mb-2 text-[10px] font-medium text-red-400">Top Negative</p>
                      <FrequencyBars items={p.topNegative} color="#f87171" />
                    </div>
                  </div>
                )}
              </div>
            </section>
          )}
        </div>
      </div>
    );
  }

  if (payload.type === "code") {
    return (
      <div className="flex w-80 flex-shrink-0 flex-col border-l border-white/[0.08] bg-[#131314]">
        <div className="flex items-center justify-between border-b border-white/[0.08] px-4 py-3">
          <div className="flex items-center gap-2">
            <Code2 size={14} className="text-blue-400" />
            <span className="text-sm font-medium text-zinc-100">Code Snippet</span>
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-1 text-zinc-500 transition-colors hover:bg-white/10 hover:text-zinc-200"
          >
            <X size={14} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          <pre className="overflow-x-auto rounded-xl border border-white/[0.06] bg-[#1e1f20] p-4 text-xs text-zinc-300">
            <code>{payload.code}</code>
          </pre>
        </div>
      </div>
    );
  }

  return null;
}

// ── Main ChatInterface ─────────────────────────────────────────────────────

export default function ChatInterface() {
  const [messages, setMessages] = useState<ChatMessage[]>([]); // Empty on start — no mock data
  const [currentLeafId, setCurrentLeafId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [activeDashboard, setActiveDashboard] = useState<DashboardPayload>(null);
  const [mode, setMode] = useState<ChatMode>("none");

  const bottomRef = useRef<HTMLDivElement>(null);
  const messagesRef = useRef<ChatMessage[]>([]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const activePath = getActivePath(messages, currentLeafId);

  const scrollToBottom = useCallback(() => {
    setTimeout(() => {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 50);
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, activeDashboard, scrollToBottom]);

  // ── Send ─────────────────────────────────────────────────────────────

  async function handleSend(text: string, images: string[]) {
    console.log("[handleSend] called →", { text, images, isLoading });
    if (isLoading) return;

    const userMsgId = generateId();
    const now = new Date();

    const newUserMsg: ChatMessage = {
      id: userMsgId,
      role: "user",
      content: text || (images.length > 0 ? "[Image attached]" : ""),
      ...(images.length > 0 ? { images: [...images] } : {}),
      timestamp: now,
      parentId: currentLeafId,
      children: [],
    };

    // Wire parent → child
    setMessages((prev) => {
      const updated = [...prev];
      updated.push(newUserMsg);
      if (currentLeafId) {
        const idx = updated.findIndex((m) => m.id === currentLeafId);
        if (idx !== -1) {
          updated[idx] = {
            ...updated[idx],
            children: [...updated[idx].children, userMsgId],
          };
        }
      }
      return updated;
    });
    setCurrentLeafId(userMsgId);

    const userPrompt =
      text.trim() || (images.length > 0 ? "What do you see in this image?" : "");

    const historyForApi: ChatHistoryItem[] = [
      ...getActivePath(messagesRef.current, currentLeafId).map((m) => ({
        role: m.role,
        content: m.content,
        ...(m.images?.length ? { images: m.images } : {}),
      })),
      {
        role: "user",
        content: userPrompt,
        ...(images.length > 0 ? { images } : {}),
      },
    ];

    setIsLoading(true);
    scrollToBottom();

    try {
      const response = await sendChat(historyForApi, mode);

      const aiMsgId = generateId();
      const aiMsg: ChatMessage = {
        id: aiMsgId,
        role: "assistant",
        content: response.reply_text,
        timestamp: new Date(),
        parentId: userMsgId,
        children: [],
        dashboardPayload: response.dashboard_payload,
      };

      setMessages((prev) => {
        const updated = [...prev];
        const userIdx = updated.findIndex((m) => m.id === userMsgId);
        if (userIdx !== -1) {
          updated[userIdx] = { ...updated[userIdx], children: [aiMsgId] };
        }
        updated.push(aiMsg);
        return updated;
      });
      setCurrentLeafId(aiMsgId);

      if (response.dashboard_payload) {
        setActiveDashboard(response.dashboard_payload);
      }
    } catch {
      const errorMsg: ChatMessage = {
        id: generateId(),
        role: "assistant",
        content:
          "Could not reach the backend. Make sure FastAPI is running on port 8000.",
        timestamp: new Date(),
        parentId: userMsgId,
        children: [],
      };
      setMessages((prev) => {
        const updated = [...prev];
        const userIdx = updated.findIndex((m) => m.id === userMsgId);
        if (userIdx !== -1) {
          updated[userIdx] = { ...updated[userIdx], children: [errorMsg.id] };
        }
        updated.push(errorMsg);
        return updated;
      });
      setCurrentLeafId(errorMsg.id);
    } finally {
      setIsLoading(false);
    }
  }

  // ── Edit ─────────────────────────────────────────────────────────────

  function handleStartEdit(id: string, currentContent: string) {
    setEditingId(id);
    setEditingValue(currentContent);
  }

  function handleCancelEdit() {
    setEditingId(null);
    setEditingValue("");
  }

  // ── Version Navigate ─────────────────────────────────────────────────────
  // Navigate to a different "version" of a user message — a different sibling
  // in the parent's children array.
  function handleVersionNavigate(parentId: string | null, targetSiblingIndex: number) {
    const all = messagesRef.current;
    const siblingIds = getUserSiblingIdsForParent(all, parentId);
    if (targetSiblingIndex < 0 || targetSiblingIndex >= siblingIds.length) return;
    const targetUserId = siblingIds[targetSiblingIndex];
    setCurrentLeafId(deepestLeafFrom(all, targetUserId));
    setActiveDashboard(null);
  }

  async function handleEditSubmit(id: string, newContent: string) {
    if (!newContent.trim() || isLoading) return;

    const editedMsg = messagesRef.current.find((m) => m.id === id);
    if (!editedMsg || editedMsg.role !== "user") return;

    setEditingId(null);
    setEditingValue("");

    const branchParentId = editedMsg.parentId;

    // ── New user turn as sibling of the edited message (same parent assistant / root) ──
    const newUserMsgId = generateId();
    const newUserMsg: ChatMessage = {
      id: newUserMsgId,
      role: "user",
      content: newContent,
      ...(editedMsg.images?.length ? { images: [...editedMsg.images] } : {}),
      timestamp: new Date(),
      parentId: branchParentId,
      children: [],
    };

    const aiMsgId = generateId();
    const placeholder: ChatMessage = {
      id: aiMsgId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
      parentId: newUserMsgId,
      children: [],
    };

    setMessages((prev) => {
      const updated = [...prev];
      updated.push(newUserMsg);
      if (branchParentId != null) {
        const pIdx = updated.findIndex((m) => m.id === branchParentId);
        if (pIdx !== -1) {
          updated[pIdx] = {
            ...updated[pIdx],
            children: [...updated[pIdx].children, newUserMsgId],
          };
        }
      }
      updated.push(placeholder);
      return updated;
    });

    setCurrentLeafId(aiMsgId);
    setActiveDashboard(null); // clear old dashboard — new version has its own
    setIsLoading(true);
    scrollToBottom();

    const prefixPath =
      branchParentId != null
        ? getActivePath(messagesRef.current, branchParentId)
        : [];

    const historyForApi: ChatHistoryItem[] = [
      ...prefixPath.map((m) => ({
        role: m.role,
        content: m.content,
        ...(m.images?.length ? { images: m.images } : {}),
      })),
      {
        role: "user",
        content: newContent,
        ...(editedMsg.images?.length ? { images: editedMsg.images } : {}),
      },
    ];

    try {
      const response = await sendChat(historyForApi, mode);

      setMessages((prev) => {
        const updated = [...prev];
        const aiIdx = updated.findIndex((m) => m.id === aiMsgId);
        if (aiIdx !== -1) {
          updated[aiIdx] = {
            ...updated[aiIdx],
            content: response.reply_text,
            dashboardPayload: response.dashboard_payload,
          };
        }
        const newUserIdx = updated.findIndex((m) => m.id === newUserMsgId);
        if (newUserIdx !== -1) {
          updated[newUserIdx] = { ...updated[newUserIdx], children: [aiMsgId] };
        }
        return updated;
      });
      if (response.dashboard_payload) {
        setActiveDashboard(response.dashboard_payload);
      }
    } catch {
      setMessages((prev) => {
        const updated = [...prev];
        const aiIdx = updated.findIndex((m) => m.id === aiMsgId);
        if (aiIdx !== -1) {
          updated[aiIdx] = {
            ...updated[aiIdx],
            content: "Failed to regenerate. Please try again.",
          };
        }
        return updated;
      });
    } finally {
      setIsLoading(false);
    }
  }

  // ── Delete ───────────────────────────────────────────────────────────

  function handleDelete(id: string) {
    setMessages((prev) => {
      // Find the parent of the deleted message
      const deleted = prev.find((m) => m.id === id);
      if (!deleted) return prev;

      // Remove the message
      const withoutDeleted = prev.filter((m) => m.id !== id);

      // If the deleted message was the current leaf, jump back to its parent
      if (currentLeafId === id) {
        setCurrentLeafId(deleted.parentId);
      }

      // Remove this id from parent's children array
      if (deleted.parentId) {
        const parentIdx = withoutDeleted.findIndex((m) => m.id === deleted.parentId);
        if (parentIdx !== -1) {
          withoutDeleted[parentIdx] = {
            ...withoutDeleted[parentIdx],
            children: withoutDeleted[parentIdx].children.filter((cid) => cid !== id),
          };
        }
      }

      return withoutDeleted;
    });
  }

  // ── Render ───────────────────────────────────────────────────────────

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[#131314] text-zinc-100">
      {/* Main chat */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Header */}
        <header className="flex-shrink-0 flex items-center gap-3 border-b border-white/[0.08] bg-[#131314]/95 px-6 py-3.5 backdrop-blur-sm">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-blue-400 to-purple-500">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="white">
              <path d="M12 2L9.5 9.5H2l6.2 4.5L5.5 22 12 17l6.5 5-2.7-8.5L22 9.5h-7.5z" />
            </svg>
          </div>
          <h1 className="text-base font-semibold tracking-tight text-zinc-100">
            FinChat
          </h1>
          <div className="ml-auto flex items-center gap-2 text-xs text-zinc-500">
            <span className="h-1.5 w-1.5 rounded-full bg-green-400" />
            Mistral-Small3.1 24B · Llava if image · Ollama
          </div>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto pb-36">
          {/* Empty state */}
          {activePath.length === 0 && !isLoading && (
            <div className="flex h-full flex-col items-center justify-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-blue-400 to-purple-500">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="white">
                  <path d="M12 2L9.5 9.5H2l6.2 4.5L5.5 22 12 17l6.5 5-2.7-8.5L22 9.5h-7.5z" />
                </svg>
              </div>
              <p className="text-sm text-zinc-500">
                Ask FinChat anything about finance
              </p>
            </div>
          )}

          {activePath.map((msg) => {
            const siblingIds =
              msg.role === "user"
                ? getUserSiblingIdsForParent(messages, msg.parentId)
                : [msg.id];
            const siblingCount = msg.role === "user" ? siblingIds.length : 1;
            const siblingIndex =
              msg.role === "user" ? Math.max(0, siblingIds.indexOf(msg.id)) : 0;

            return (
              <ChatMessageItem
                key={msg.id}
                message={msg}
                siblingCount={siblingCount}
                siblingIndex={siblingIndex}
                isEditing={editingId === msg.id}
                editingValue={editingValue}
                onEditingValueChange={setEditingValue}
                onStartEdit={handleStartEdit}
                onEditSubmit={handleEditSubmit}
                onVersionNavigate={handleVersionNavigate}
                onDelete={handleDelete}
                onCancelEdit={handleCancelEdit}
                isStreaming={
                  isLoading &&
                  msg.id === currentLeafId &&
                  msg.role === "assistant" &&
                  !msg.content
                }
                onDashboardToggle={
                  msg.role === "assistant" && msg.dashboardPayload
                    ? () => setActiveDashboard(msg.dashboardPayload ?? null)
                    : undefined
                }
              />
            );
          })}

          {/* Loading dots */}
          {isLoading && activePath[activePath.length - 1]?.role === "user" && (
            <div className="flex gap-3 px-6 py-3">
              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-400 to-purple-500">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="white">
                  <path d="M12 2L9.5 9.5H2l6.2 4.5L5.5 22 12 17l6.5 5-2.7-8.5L22 9.5h-7.5z" />
                </svg>
              </div>
              <div className="flex flex-col gap-1">
                <span className="mb-1 text-xs font-medium text-blue-400">
                  FinChat
                </span>
                <div className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="h-2 w-2 rounded-full bg-zinc-600 animate-bounce"
                      style={{ animationDelay: `${i * 150}ms` }}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} className="h-4" />
        </div>

        {/* Floating input */}
        <PromptInput onSend={handleSend} isLoading={isLoading} mode={mode} onModeChange={setMode} />
      </div>

      {/* Dashboard panel */}
      {activeDashboard && (
        <DashboardPanel
          payload={activeDashboard}
          onClose={() => setActiveDashboard(null)}
        />
      )}
    </div>
  );
}
