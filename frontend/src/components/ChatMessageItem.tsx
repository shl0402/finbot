// frontend/src/components/ChatMessageItem.tsx
"use client";

import { useRef, useEffect } from "react";
import { Pencil, Trash2, ChevronLeft, ChevronRight, X, Check } from "lucide-react";
import BotAvatar from "./icons/BotAvatar";
import UserAvatar from "./icons/UserAvatar";
import type { ChatMessage } from "@/types/chat";

interface ChatMessageItemProps {
  message: ChatMessage;
  siblingCount: number;       // how many siblings this message has (including itself)
  siblingIndex: number;        // which index this message is among siblings (0-based)
  onStartEdit: (id: string, currentContent: string) => void;
  onEditSubmit: (id: string, newContent: string) => void;
  onVersionNavigate: (parentId: string | null, siblingIndex: number) => void; // navigate to a sibling
  onDelete: (id: string) => void;
  isEditing: boolean;
  editingValue: string;
  onEditingValueChange: (v: string) => void;
  onCancelEdit: () => void;
  isStreaming?: boolean;
  onDashboardToggle?: () => void;
}

export default function ChatMessageItem({
  message,
  siblingCount,
  siblingIndex,
  onStartEdit,
  onEditSubmit,
  onVersionNavigate,
  onDelete,
  isEditing,
  editingValue,
  onEditingValueChange,
  onCancelEdit,
  isStreaming = false,
  onDashboardToggle,
}: ChatMessageItemProps) {
  const isUser = message.role === "user";
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const hasSiblings = siblingCount > 1;

  // Auto-resize textarea when editing value changes
  useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.focus();
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [isEditing, editingValue]);

  function handleTextareaChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    onEditingValueChange(e.target.value);
    const ta = e.target;
    ta.style.height = "auto";
    ta.style.height = `${ta.scrollHeight}px`;
  }

  function handleEditKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (editingValue.trim()) onEditSubmit(message.id, editingValue);
    }
    if (e.key === "Escape") onCancelEdit();
  }

  function handleSubmitEdit() {
    if (!editingValue.trim()) return;
    onEditSubmit(message.id, editingValue);
  }

  function formatTime(date: Date) {
    return new Intl.DateTimeFormat("en", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(date));
  }

  return (
    <div
      className={`flex w-full py-2 ${isUser ? "flex-row-reverse justify-start gap-3 pl-2 pr-4" : "flex-row gap-2 pl-2 pr-6"}`}
    >
      {/* Avatar */}
      <div className="flex-shrink-0 mt-1">
        {isUser ? <UserAvatar /> : <BotAvatar />}
      </div>

      {/* Content column — user: shrink-to-fit so text sits next to avatar, not full-width */}
      <div
        className={`flex flex-col min-w-0 ${
          isUser ? "max-w-[min(42rem,calc(100%-3rem))] shrink items-end" : "flex-1 items-start"
        }`}
      >
        {/* Role label */}
        <span
          className={`mb-1 text-xs font-medium ${
            isUser ? "text-zinc-500" : "text-blue-400"
          }`}
        >
          {isUser ? "You" : "FinChat"}
        </span>

        {/* ── Editing mode ── */}
        {isEditing ? (
          <div className="w-full max-w-2xl">
            <textarea
              ref={textareaRef}
              value={editingValue}
              onChange={handleTextareaChange}
              onKeyDown={handleEditKeyDown}
              className="w-full resize-none rounded-2xl border border-white/10 bg-[#2a2a2a] px-4 py-3 text-[15px] leading-relaxed text-zinc-100 outline-none focus:ring-1 focus:ring-blue-500/50"
              rows={3}
            />
            <div className="mt-2 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={onCancelEdit}
                className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs text-zinc-400 transition-colors hover:bg-white/10 hover:text-zinc-200"
              >
                <X size={12} />
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSubmitEdit}
                disabled={!editingValue.trim()}
                className="flex items-center gap-1.5 rounded-full bg-[#a8c7fa] px-3 py-1.5 text-xs font-medium text-[#062e6f] transition-colors hover:bg-[#c2d7fc] disabled:opacity-40"
              >
                <Check size={12} />
                Regenerate
              </button>
            </div>
          </div>
        ) : (
          /* ── View mode ── */
          <div className={isUser ? "w-fit max-w-full" : "w-full max-w-2xl"}>
            {message.images && message.images.length > 0 && (
              <div className={`mb-2 flex flex-col gap-2 ${isUser ? "items-end" : "items-start"}`}>
                {message.images.map((src, i) => (
                  // data: URLs from FileReader — not suitable for next/image without remotePatterns
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    key={i}
                    src={src}
                    alt=""
                    className="max-h-56 max-w-full rounded-2xl border border-white/[0.08] object-contain"
                  />
                ))}
              </div>
            )}
            {/* Message text */}
            <p
              className={`whitespace-pre-wrap break-words text-[15px] leading-relaxed text-zinc-100 ${
                isUser ? "text-right" : "text-left"
              }`}
            >
              {message.content}
              {isStreaming && (
                <span className="cursor-blink ml-0.5 text-blue-400">▊</span>
              )}
            </p>

            {/* Footer row */}
            <div
              className={`mt-1 flex items-center gap-1 ${
                isUser ? "justify-end" : "justify-start"
              }`}
            >
              {/* Version navigator — user messages with siblings */}
              {isUser && hasSiblings && (
                <div className="mr-1 inline-flex items-center gap-0.5 rounded-full border border-white/10 bg-white/[0.04] px-1.5 py-0.5 text-[11px] text-zinc-500">
                  <button
                    type="button"
                    onClick={() =>
                      onVersionNavigate(message.parentId, Math.max(0, siblingIndex - 1))
                    }
                    disabled={siblingIndex === 0}
                    className="rounded p-0.5 transition-colors hover:bg-white/10 hover:text-zinc-200 disabled:cursor-default disabled:opacity-30"
                  >
                    <ChevronLeft size={11} />
                  </button>
                  <span className="min-w-[2.25rem] select-none text-center tabular-nums">
                    {siblingIndex + 1}/{siblingCount}
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      onVersionNavigate(message.parentId, Math.min(siblingCount - 1, siblingIndex + 1))
                    }
                    disabled={siblingIndex === siblingCount - 1}
                    className="rounded p-0.5 transition-colors hover:bg-white/10 hover:text-zinc-200 disabled:cursor-default disabled:opacity-30"
                  >
                    <ChevronRight size={11} />
                  </button>
                </div>
              )}

              {/* Timestamp */}
              <span className="text-[11px] text-zinc-600">
                {formatTime(message.timestamp)}
              </span>

              {/* Edit + Delete — user messages */}
              {isUser && (
                <div className="ml-1 flex items-center gap-0.5 text-zinc-600">
                  <button
                    type="button"
                    onClick={() => onStartEdit(message.id, message.content)}
                    title="Edit"
                    className="rounded p-0.5 transition-colors hover:bg-white/10 hover:text-zinc-200"
                  >
                    <Pencil size={12} />
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(message.id)}
                    title="Delete"
                    className="rounded p-0.5 transition-colors hover:bg-white/10 hover:text-red-400"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              )}

              {/* Delete — AI messages */}
              {!isUser && (
                <button
                  type="button"
                  onClick={() => onDelete(message.id)}
                  title="Delete"
                  className="ml-1 rounded p-0.5 text-zinc-600 transition-colors hover:bg-white/10 hover:text-red-400"
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>

            {/* Dashboard button for AI messages */}
            {message.role === "assistant" && message.dashboardPayload && (
              <button
                type="button"
                onClick={onDashboardToggle}
                className="mt-2 flex items-center gap-1.5 rounded-full border border-blue-400/30 px-3 py-1.5 text-xs text-blue-400 transition-colors hover:border-blue-400/60 hover:bg-blue-400/10"
              >
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <rect x="3" y="3" width="7" height="7" rx="1" />
                  <rect x="14" y="3" width="7" height="7" rx="1" />
                  <rect x="3" y="14" width="7" height="7" rx="1" />
                  <rect x="14" y="14" width="7" height="7" rx="1" />
                </svg>
                View Dashboard
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
