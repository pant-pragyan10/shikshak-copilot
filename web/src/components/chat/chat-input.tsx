"use client";

import * as React from "react";
import { ArrowUp, Mic, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  streaming,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  streaming: boolean;
}) {
  const ref = React.useRef<HTMLTextAreaElement>(null);

  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !streaming) onSend();
    }
  };

  return (
    <div className="relative flex items-end gap-2 rounded-[--radius-lg] border border-border bg-card p-2 shadow-sm focus-within:ring-2 focus-within:ring-ring">
      {/* Voice input is intentionally a disabled placeholder (STT is out of scope). */}
      <Tooltip content="Voice input — coming soon">
        <span>
          <Button variant="ghost" size="icon" disabled aria-label="Voice input (coming soon)">
            <Mic className="size-[18px]" />
          </Button>
        </span>
      </Tooltip>

      <textarea
        ref={ref}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        rows={1}
        placeholder="Ask anything — grade an answer, plan a lesson, check in…"
        className="max-h-[200px] flex-1 resize-none bg-transparent py-2 text-sm outline-none placeholder:text-muted-foreground"
      />

      {streaming ? (
        <Button size="icon" variant="secondary" onClick={onStop} aria-label="Stop">
          <Square className="size-4 fill-current" />
        </Button>
      ) : (
        <Button
          size="icon"
          onClick={onSend}
          disabled={!value.trim()}
          aria-label="Send"
          className={cn("transition-transform", value.trim() && "scale-100")}
        >
          <ArrowUp className="size-[18px]" />
        </Button>
      )}
    </div>
  );
}
