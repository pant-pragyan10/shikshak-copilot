"use client";

import { motion } from "framer-motion";
import { CircleCheck, Lightbulb, ShieldAlert, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import type { GradedResult } from "@/lib/types";
import { cn } from "@/lib/utils";

function ScoreRing({ percentage, needsReview }: { percentage: number; needsReview: boolean }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, percentage));
  const color = needsReview
    ? "var(--color-warning)"
    : pct >= 75
      ? "var(--color-success)"
      : pct >= 40
        ? "var(--color-primary)"
        : "var(--color-danger)";
  return (
    <div className="relative size-24 shrink-0">
      <svg viewBox="0 0 80 80" className="size-24 -rotate-90">
        <circle cx="40" cy="40" r={r} fill="none" stroke="var(--color-muted)" strokeWidth="7" />
        <motion.circle
          cx="40"
          cy="40"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c - (c * pct) / 100 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-xl font-semibold tabular-nums">{needsReview ? "—" : `${Math.round(pct)}%`}</span>
      </div>
    </div>
  );
}

function List({ items, tone }: { items: string[]; tone: "success" | "primary" }) {
  const Icon = tone === "success" ? CircleCheck : Lightbulb;
  return (
    <ul className="space-y-1.5">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2 text-sm">
          <Icon className={cn("mt-0.5 size-4 shrink-0", tone === "success" ? "text-success" : "text-primary")} />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

export function GradedResultCard({ result }: { result: GradedResult }) {
  const needsReview = result.status === "needs_review";

  return (
    <Card className="animate-fade-in overflow-hidden">
      <div className="flex items-center gap-5 border-b border-border p-5">
        <ScoreRing percentage={result.percentage} needsReview={needsReview} />
        <div className="min-w-0">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            {needsReview ? (
              <Badge variant="warning">
                <ShieldAlert className="size-3" />
                Needs review
              </Badge>
            ) : (
              <Badge variant="success">
                <CircleCheck className="size-3" />
                Graded
              </Badge>
            )}
            <Badge variant="outline">
              {result.rubric_source === "auto" ? "Auto-generated rubric" : "Your rubric"}
            </Badge>
          </div>
          {!needsReview && (
            <p className="text-2xl font-semibold tabular-nums">
              {result.total_awarded}
              <span className="text-muted-foreground">/{result.total_max} marks</span>
            </p>
          )}
          {result.overall_comment && (
            <p className="mt-1 text-sm text-muted-foreground">{result.overall_comment}</p>
          )}
        </div>
      </div>

      {needsReview ? (
        <div className="p-5">
          <div className="rounded-[--radius-md] border border-warning/30 bg-warning/10 p-4 text-sm">
            <p className="font-medium text-foreground">This wasn&apos;t graded automatically.</p>
            <p className="mt-1 text-muted-foreground">
              The answer was illegible, looked like it answered a different question, or the model
              wasn&apos;t confident — so no marks were fabricated. Please review it yourself.
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-5 p-5">
          <div className="space-y-4">
            {result.scores.map((s, i) => {
              const pct = s.max_marks ? (s.awarded_marks / s.max_marks) * 100 : 0;
              return (
                <div key={i}>
                  <div className="mb-1 flex items-baseline justify-between gap-3">
                    <span className="text-sm font-medium">{s.criterion_name}</span>
                    <span className="shrink-0 text-sm tabular-nums text-muted-foreground">
                      {s.awarded_marks}/{s.max_marks}
                    </span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-muted">
                    <motion.div
                      className="h-full rounded-full bg-primary"
                      initial={{ width: 0 }}
                      animate={{ width: `${pct}%` }}
                      transition={{ duration: 0.6, ease: "easeOut", delay: i * 0.05 }}
                    />
                  </div>
                  <p className="mt-1.5 text-sm text-muted-foreground">{s.justification}</p>
                </div>
              );
            })}
          </div>

          {(result.strengths.length > 0 || result.improvements.length > 0) && (
            <div className="grid gap-4 sm:grid-cols-2">
              {result.strengths.length > 0 && (
                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Strengths
                  </p>
                  <List items={result.strengths} tone="success" />
                </div>
              )}
              {result.improvements.length > 0 && (
                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    To improve
                  </p>
                  <List items={result.improvements} tone="primary" />
                </div>
              )}
            </div>
          )}

          {result.adjustments.length > 0 && (
            <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
              <Sparkles className="mt-0.5 size-3.5 shrink-0" />
              Consistency guard: {result.adjustments.join(" ")}
            </p>
          )}
        </div>
      )}
    </Card>
  );
}
