"use client";

import { motion } from "framer-motion";
import { AgentOutputCard } from "@/components/cards/agent-output";
import { IntentBadge } from "@/components/cards/badges";
import { Spinner } from "@/components/ui/misc";
import { LogoMark } from "@/components/brand/logo";
import type { AgentOutput, Intent } from "@/lib/types";
import { cn } from "@/lib/utils";

export interface UiMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  intent?: Intent;
  agentOutput?: AgentOutput | null;
  streaming?: boolean;
}

export function MessageBubble({ message }: { message: UiMessage }) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-end"
      >
        <div className="max-w-[80%] rounded-[--radius-lg] rounded-br-md bg-primary px-4 py-2.5 text-sm text-primary-foreground shadow-sm">
          {message.text}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-3"
    >
      <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center">
        <LogoMark className="size-7" />
      </div>
      <div className="min-w-0 flex-1 space-y-3">
        {message.intent && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>Routed to</span>
            <IntentBadge intent={message.intent} />
          </div>
        )}
        {message.text ? (
          <div className={cn("prose-chat text-sm leading-relaxed", "whitespace-pre-wrap")}>
            {message.text}
          </div>
        ) : message.streaming ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Spinner /> Thinking…
          </div>
        ) : null}
        {message.agentOutput && <AgentOutputCard output={message.agentOutput} />}
      </div>
    </motion.div>
  );
}
