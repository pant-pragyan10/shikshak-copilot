"use client";

import {
  ClipboardCheck,
  Clock,
  FileText,
  GraduationCap,
  Home,
  Package,
  Printer,
  Quote,
  Target,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { GroundingBadge } from "@/components/cards/badges";
import type { LessonPlan } from "@/lib/types";

function Section({
  icon: Icon,
  title,
  items,
}: {
  icon: typeof Target;
  title: string;
  items: string[];
}) {
  if (!items.length) return null;
  return (
    <div>
      <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <Icon className="size-3.5" />
        {title}
      </p>
      <ul className="space-y-1.5 pl-1">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2 text-sm">
            <span className="mt-1.5 size-1 shrink-0 rounded-full bg-primary" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function LessonPlanCard({ plan }: { plan: LessonPlan }) {
  const meta = [plan.subject, plan.grade && `Class ${plan.grade}`, plan.board]
    .filter(Boolean)
    .join(" · ");

  return (
    <Card className="animate-fade-in overflow-hidden">
      <div className="border-b border-border p-5">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <GroundingBadge grounding={plan.grounding} />
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="size-3.5" />
            {plan.duration_minutes} min
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto"
            onClick={() => window.print()}
          >
            <Printer className="size-4" />
            Print
          </Button>
        </div>
        <h3 className="font-display text-xl font-medium leading-tight">{plan.topic}</h3>
        {meta && <p className="mt-1 text-sm text-muted-foreground">{meta}</p>}
        {plan.disclaimer && (
          <div className="mt-3 rounded-[--radius-md] border border-warning/30 bg-warning/10 p-3 text-sm text-muted-foreground">
            {plan.disclaimer}
          </div>
        )}
      </div>

      <div className="space-y-6 p-5">
        <Section icon={Target} title="Objectives" items={plan.objectives} />

        {plan.timeline.length > 0 && (
          <div>
            <p className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <Clock className="size-3.5" />
              Timeline
            </p>
            <ol className="relative space-y-4 border-l border-border pl-5">
              {plan.timeline.map((seg, i) => (
                <li key={i} className="relative">
                  <span className="absolute -left-[26px] top-0.5 flex size-4 items-center justify-center rounded-full bg-primary/15 ring-4 ring-background">
                    <span className="size-1.5 rounded-full bg-primary" />
                  </span>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-sm font-medium">{seg.title}</span>
                    <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                      {seg.minutes} min
                    </span>
                  </div>
                  {seg.activities.length > 0 && (
                    <ul className="mt-1 space-y-1">
                      {seg.activities.map((a, j) => (
                        <li key={j} className="flex gap-2 text-sm text-muted-foreground">
                          <span className="mt-1.5 size-1 shrink-0 rounded-full bg-border" />
                          {a}
                        </li>
                      ))}
                    </ul>
                  )}
                  {seg.teacher_notes && (
                    <p className="mt-1 text-xs italic text-muted-foreground">{seg.teacher_notes}</p>
                  )}
                </li>
              ))}
            </ol>
          </div>
        )}

        <div className="grid gap-6 sm:grid-cols-2">
          <Section icon={Package} title="Materials" items={plan.materials} />
          <Section icon={ClipboardCheck} title="Assessment ideas" items={plan.assessment_ideas} />
          <Section icon={Home} title="Homework" items={plan.homework} />
          <Section icon={Users} title="Differentiation" items={plan.differentiation} />
        </div>

        {plan.citations.length > 0 && (
          <div className="rounded-[--radius-md] border border-border bg-muted/40 p-4">
            <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <Quote className="size-3.5" />
              Grounded in these curriculum sources
            </p>
            <div className="space-y-2.5">
              {plan.citations.map((c, i) => (
                <div key={i} className="text-sm">
                  <p className="flex items-center gap-1.5 font-medium">
                    <FileText className="size-3.5 text-primary" />
                    {c.source}
                  </p>
                  <p className="mt-0.5 line-clamp-2 pl-5 text-xs text-muted-foreground">
                    &ldquo;{c.snippet}&rdquo;
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {plan.grounding === "general_knowledge" && plan.citations.length === 0 && (
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <GraduationCap className="size-3.5" />
            No curriculum sources matched — treat this as a general starting point.
          </p>
        )}
      </div>
    </Card>
  );
}
