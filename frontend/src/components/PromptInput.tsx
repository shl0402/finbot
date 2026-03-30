// frontend/src/components/PromptInput.tsx
"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { ArrowUp, ImageIcon, X, Sparkles, ChevronDown, BarChart2, TrendingUp } from "lucide-react";
import type { ChatMode } from "@/types/chat";

interface PromptInputProps {
  onSend: (text: string, images: string[]) => void;
  isLoading: boolean;
  mode: ChatMode;
  onModeChange: (mode: ChatMode) => void;
}

const MODES: { value: ChatMode; label: string; icon: React.ReactNode }[] = [
  { value: "none", label: "No Tool", icon: null },
  { value: "market_discovery", label: "Market Discovery", icon: <TrendingUp size={12} /> },
  { value: "stock_deep_analysis", label: "Stock Deep Analysis", icon: <BarChart2 size={12} /> },
];

export default function PromptInput({ onSend, isLoading, mode, onModeChange }: PromptInputProps) {
  const [text, setText] = useState("");
  const [images, setImages] = useState<string[]>([]); // base64 data URLs
  const [modeMenuOpen, setModeMenuOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const modeMenuRef = useRef<HTMLDivElement>(null);

  const autoResize = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 144)}px`;
  }, []);

  // Close mode menu when clicking outside
  useEffect(() => {
    if (!modeMenuOpen) return;
    function handler(e: MouseEvent) {
      if (modeMenuRef.current && !modeMenuRef.current.contains(e.target as Node)) {
        setModeMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [modeMenuOpen]);

  function handleTextChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setText(e.target.value);
    autoResize();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      doSend();
    }
  }

  function doSend() {
    const trimmed = text.trim();
    console.log("[doSend] fired →", { trimmed, imageCount: images.length, isLoading, mode });
    if (!trimmed && images.length === 0) return;
    if (isLoading) return;
    onSend(trimmed, images);
    setText("");
    setImages([]);
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    const remaining = 5 - images.length;
    files.slice(0, remaining).forEach((file) => {
      if (!file.type.startsWith("image/")) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        setImages((prev) => [...prev, ev.target?.result as string]);
      };
      reader.readAsDataURL(file);
    });
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  const canSend = (text.trim().length > 0 || images.length > 0) && !isLoading;

  return (
    <div className="fixed inset-x-0 bottom-0 z-40 flex flex-col items-center gap-2 px-4 pb-5 pt-2">
      {/* Gradient fade above messages — pure decoration, no interaction */}
      <div
        aria-hidden="true"
        className="absolute inset-x-0 bottom-0 h-28 w-full bg-gradient-to-t from-[#131314] via-[#131314]/80 to-transparent pointer-events-none"
      />

      {/* Image thumbnails */}
      {images.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {images.map((src, i) => (
            <div key={i} className="relative">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={src}
                alt={`Upload ${i + 1}`}
                className="h-16 w-16 rounded-xl border border-white/10 object-cover"
              />
              <button
                type="button"
                aria-label="Remove image"
                onClick={() => setImages((p) => p.filter((_, j) => j !== i))}
                className="absolute -top-1.5 -right-1.5 flex h-5 w-5 cursor-pointer items-center justify-center rounded-full bg-black/70 text-white hover:bg-red-500 transition-colors"
              >
                <X size={9} />
              </button>
            </div>
          ))}
          {images.length < 5 && (
            <button
              type="button"
              aria-label="Add more images"
              onClick={() => fileInputRef.current?.click()}
              className="flex h-16 w-16 cursor-pointer items-center justify-center rounded-xl border border-dashed border-white/20 text-white/40 hover:border-white/40 hover:text-white/60 transition-colors"
            >
              <ImageIcon size={20} />
            </button>
          )}
        </div>
      )}

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        onChange={handleFileChange}
      />

      {/* Pill bar */}
      <div
        className={[
          "flex w-full max-w-3xl cursor-default items-end gap-2 rounded-[28px] border border-white/10 bg-[#1e1f20] px-4 py-2.5 shadow-[0_8px_32px_rgba(0,0,0,0.45)] backdrop-blur-xl",
          isLoading ? "opacity-60" : "",
        ].join(" ")}
      >
        {/* Mode selector pill */}
        <div className="relative mb-1" ref={modeMenuRef}>
          <button
            type="button"
            aria-label="Select tool mode"
            aria-expanded={modeMenuOpen}
            onClick={() => setModeMenuOpen((v) => !v)}
            className={[
              "flex h-8 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium transition-colors",
              mode === "none"
                ? "border-white/15 text-zinc-400 hover:border-white/25 hover:text-zinc-200"
                : "border-blue-400/40 text-blue-400 hover:border-blue-400/70 hover:bg-blue-400/10",
            ].join(" ")}
          >
            {mode !== "none" && (
              <span className="flex items-center gap-1">
                {MODES.find((m) => m.value === mode)?.icon}
                {MODES.find((m) => m.value === mode)?.label}
              </span>
            )}
            {mode === "none" && "Tools"}
            <ChevronDown size={11} className={modeMenuOpen ? "rotate-180" : ""} />
          </button>

          {modeMenuOpen && (
            <div className="absolute bottom-full mb-2 left-0 z-50 flex flex-col gap-0.5 rounded-xl border border-white/[0.08] bg-[#1e1f20] p-1 shadow-xl min-w-44">
              {MODES.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  onClick={() => {
                    onModeChange(m.value);
                    setModeMenuOpen(false);
                  }}
                  className={[
                    "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                    mode === m.value
                      ? "bg-blue-400/15 text-blue-400"
                      : "text-zinc-300 hover:bg-white/10 hover:text-zinc-100",
                  ].join(" ")}
                >
                  {m.icon && <span className="flex items-center">{m.icon}</span>}
                  <span>{m.label}</span>
                  {mode === m.value && (
                    <span className="ml-auto text-[10px] text-blue-400/70">active</span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Image attach button */}
        <button
          type="button"
          aria-label="Attach image"
          onClick={() => fileInputRef.current?.click()}
          className="mb-1 flex h-8 w-8 cursor-pointer items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-white/10 hover:text-zinc-100 disabled:text-zinc-700"
          disabled={isLoading || images.length >= 5}
        >
          <ImageIcon size={18} strokeWidth={1.75} />
        </button>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleTextChange}
          onKeyDown={handleKeyDown}
          placeholder="Ask FinChat..."
          rows={1}
          className="max-h-36 min-h-[24px] flex-1 cursor-text resize-none bg-transparent py-2 text-[15px] leading-relaxed text-zinc-100 placeholder:text-zinc-500 outline-none"
        />

        {/* Send button */}
        <button
          type="button"
          aria-label="Send message"
          onClick={doSend}
          className={[
            "mb-1 flex h-9 w-9 cursor-pointer items-center justify-center rounded-full border-none transition-all active:scale-95",
            canSend
              ? "bg-[#a8c7fa] text-[#062e6f] hover:bg-[#c2d7fc]"
              : "bg-zinc-700/50 text-zinc-500",
          ].join(" ")}
        >
          {isLoading ? (
            <Sparkles size={18} className="animate-pulse" strokeWidth={1.75} />
          ) : (
            <ArrowUp size={18} strokeWidth={2} />
          )}
        </button>
      </div>
    </div>
  );
}
