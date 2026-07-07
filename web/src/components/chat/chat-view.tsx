"use client";

import * as React from "react";
import { MessageSquarePlus } from "lucide-react";
import { toast } from "sonner";
import { ChatHero } from "@/components/chat/hero";
import { ChatInput } from "@/components/chat/chat-input";
import { MessageBubble, type UiMessage } from "@/components/chat/message-bubble";
import { IntentBadge } from "@/components/cards/badges";
import { Button } from "@/components/ui/button";
import { ToolShell } from "@/components/layout/tool-shell";
import { streamChat } from "@/lib/sse";
import { useTeacher } from "@/lib/teacher";
import type { Intent } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Session {
  id: string;
  title: string;
  serverSessionId?: string;
  messages: UiMessage[];
}

const uid = () =>
  typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;

export function ChatView() {
  const { teacherId } = useTeacher();
  const [sessions, setSessions] = React.useState<Session[]>([{ id: uid(), title: "New chat", messages: [] }]);
  const [activeId, setActiveId] = React.useState<string>(() => sessions[0].id);
  const [input, setInput] = React.useState("");
  const [streaming, setStreaming] = React.useState(false);
  const [liveIntent, setLiveIntent] = React.useState<Intent | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);
  const scrollRef = React.useRef<HTMLDivElement>(null);

  const active = sessions.find((s) => s.id === activeId) ?? sessions[0];

  React.useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [active.messages]);

  const patchMessage = React.useCallback(
    (sessionId: string, messageId: string, patch: Partial<UiMessage>) => {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId
            ? { ...s, messages: s.messages.map((m) => (m.id === messageId ? { ...m, ...patch } : m)) }
            : s,
        ),
      );
    },
    [],
  );

  const newChat = () => {
    if (streaming) return;
    const s: Session = { id: uid(), title: "New chat", messages: [] };
    setSessions((prev) => [s, ...prev]);
    setActiveId(s.id);
    setLiveIntent(null);
  };

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || streaming) return;
    setInput("");
    setLiveIntent(null);

    const userMsg: UiMessage = { id: uid(), role: "user", text: message };
    const assistantId = uid();
    const assistantMsg: UiMessage = { id: assistantId, role: "assistant", text: "", streaming: true };
    const sessionId = active.id;

    setSessions((prev) =>
      prev.map((s) =>
        s.id === sessionId
          ? {
              ...s,
              title: s.messages.length === 0 ? message.slice(0, 40) : s.title,
              messages: [...s.messages, userMsg, assistantMsg],
            }
          : s,
      ),
    );

    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(
        { teacher_id: teacherId, message, session_id: active.serverSessionId ?? null },
        {
          onIntent: (e) => {
            setLiveIntent(e.intent);
            patchMessage(sessionId, assistantId, { intent: e.intent });
          },
          onMessage: (e) => patchMessage(sessionId, assistantId, { text: e.text }),
          onAgentOutput: (e) => patchMessage(sessionId, assistantId, { agentOutput: e }),
          onDone: (e) => {
            setSessions((prev) =>
              prev.map((s) => (s.id === sessionId ? { ...s, serverSessionId: e.session_id } : s)),
            );
          },
          onError: (e) => {
            toast.error(e.message);
            patchMessage(sessionId, assistantId, { text: e.message });
          },
        },
        controller.signal,
      );
    } catch (err) {
      if (!controller.signal.aborted) {
        const msg = err instanceof Error ? err.message : "Something went wrong.";
        toast.error(msg);
        patchMessage(sessionId, assistantId, { text: msg });
      }
    } finally {
      patchMessage(sessionId, assistantId, { streaming: false });
      setStreaming(false);
      abortRef.current = null;
    }
  };

  const stop = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  const aside = (
    <div className="space-y-5">
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Current turn
        </p>
        {liveIntent ? (
          <div className="rounded-[--radius-md] border border-border bg-card p-3">
            <p className="mb-1.5 text-xs text-muted-foreground">Detected intent</p>
            <IntentBadge intent={liveIntent} />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Send a message to see it route.</p>
        )}
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Sessions</p>
          <Button variant="ghost" size="sm" onClick={newChat} className="h-7 px-2">
            <MessageSquarePlus className="size-4" />
          </Button>
        </div>
        <div className="space-y-1">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => setActiveId(s.id)}
              className={cn(
                "w-full truncate rounded-[--radius-md] px-3 py-2 text-left text-sm transition-colors",
                s.id === activeId ? "bg-primary/12 text-primary" : "text-muted-foreground hover:bg-muted",
              )}
            >
              {s.title || "New chat"}
            </button>
          ))}
        </div>
      </div>
    </div>
  );

  return (
    <ToolShell aside={aside} asideTitle="Chat context">
      <div className="flex h-full flex-col">
        <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-slim">
          {active.messages.length === 0 ? (
            <ChatHero onExample={(p) => send(p)} />
          ) : (
            <div className="mx-auto w-full max-w-3xl space-y-6 px-5 py-6">
              {active.messages.map((m) => (
                <MessageBubble key={m.id} message={m} />
              ))}
            </div>
          )}
        </div>
        <div className="border-t border-border bg-background/80 backdrop-blur">
          <div className="mx-auto w-full max-w-3xl px-5 py-4">
            <ChatInput
              value={input}
              onChange={setInput}
              onSend={() => send(input)}
              onStop={stop}
              streaming={streaming}
            />
            <p className="mt-2 text-center text-xs text-muted-foreground">
              Shikshak Copilot can make mistakes. Grades and plans are drafts — review before use.
            </p>
          </div>
        </div>
      </div>
    </ToolShell>
  );
}
