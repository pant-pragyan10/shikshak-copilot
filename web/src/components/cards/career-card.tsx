"use client";

import { ArrowRight, Compass, Info, Quote, Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { CareerGroundingBadge } from "@/components/cards/badges";
import type { CareerGuidance } from "@/lib/types";

export function CareerCard({ guidance }: { guidance: CareerGuidance }) {
  return (
    <Card className="animate-fade-in overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-border p-5">
        <div className="flex size-9 items-center justify-center rounded-full bg-primary/12 text-primary">
          <Compass className="size-[18px]" />
        </div>
        <p className="text-sm font-medium">Career directions</p>
        <span className="ml-auto">
          <CareerGroundingBadge grounding={guidance.grounding} />
        </span>
      </div>

      {guidance.disclaimer && (
        <div className="border-b border-border bg-warning/8 px-5 py-3 text-sm text-muted-foreground">
          {guidance.disclaimer}
        </div>
      )}

      <div className="space-y-4 p-5">
        {guidance.matched_paths.map((path, i) => (
          <div key={i} className="rounded-[--radius-md] border border-border p-4">
            <div className="mb-1.5 flex flex-wrap items-center gap-2">
              <h4 className="font-medium">{path.title}</h4>
              {path.source && (
                <Badge variant="default" className="gap-1">
                  <Quote className="size-3" />
                  {path.source}
                </Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground">{path.why_it_fits}</p>

            {path.skills_to_build.length > 0 && (
              <div className="mt-3">
                <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <Wrench className="size-3.5" />
                  Skills to build
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {path.skills_to_build.map((s, j) => (
                    <span
                      key={j}
                      className="rounded-full bg-muted px-2.5 py-1 text-xs text-foreground"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {path.first_steps.length > 0 && (
              <div className="mt-3">
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  First steps
                </p>
                <ol className="space-y-1.5">
                  {path.first_steps.map((step, j) => (
                    <li key={j} className="flex gap-2 text-sm">
                      <ArrowRight className="mt-0.5 size-4 shrink-0 text-primary" />
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        ))}

        {guidance.honest_caveats.length > 0 && (
          <div className="rounded-[--radius-md] border border-border bg-muted/40 p-4">
            <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <Info className="size-3.5" />
              Honest caveats
            </p>
            <ul className="space-y-1.5">
              {guidance.honest_caveats.map((c, i) => (
                <li key={i} className="text-sm text-muted-foreground">
                  {c}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}
