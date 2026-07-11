"use client";

import { motion } from "framer-motion";
import { BookOpen, Compass, HeartPulse, PenLine, type LucideIcon } from "lucide-react";
import { LogoMark } from "@/components/brand/logo";

const EXAMPLES: { icon: LucideIcon; title: string; prompt: string }[] = [
  {
    icon: PenLine,
    title: "Grade an answer",
    prompt:
      "Grade this. Question: State Newton's second law of motion. Answer: Force equals mass times acceleration, F = ma.",
  },
  {
    icon: BookOpen,
    title: "Plan a lesson",
    prompt: "Plan a 40-minute class 8 science lesson on reflection of light.",
  },
  {
    icon: HeartPulse,
    title: "Check in on workload",
    prompt: "I'm feeling drained this week — how am I doing?",
  },
  {
    icon: Compass,
    title: "Explore career growth",
    prompt: "I'm curious about moving into edtech content roles. What are my options?",
  },
];

export function ChatHero({ onExample }: { onExample: (prompt: string) => void }) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-5 py-10 text-center sm:py-16">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: "spring", stiffness: 200, damping: 18 }}
      >
        <LogoMark className="size-14" />
      </motion.div>
      <h1 className="mt-5 font-display text-3xl font-medium tracking-tight text-balance sm:text-4xl">
        Your teaching copilot
      </h1>
      <p className="mt-3 max-w-lg text-balance text-muted-foreground">
        Grade answers, plan curriculum-grounded lessons, reflect on workload, and explore career
        growth — one assistant that routes your request to the right specialist.
      </p>

      <div className="mt-8 grid w-full gap-3 sm:grid-cols-2">
        {EXAMPLES.map((ex, i) => {
          const Icon = ex.icon;
          return (
            <motion.button
              key={ex.title}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 * i }}
              onClick={() => onExample(ex.prompt)}
              className="group flex flex-col gap-1.5 rounded-[--radius-lg] border border-border bg-card p-4 text-left transition-colors hover:border-primary/40 hover:bg-accent"
            >
              <span className="flex items-center gap-2 text-sm font-medium">
                <Icon className="size-4 text-primary" />
                {ex.title}
              </span>
              <span className="line-clamp-2 text-xs text-muted-foreground">{ex.prompt}</span>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
