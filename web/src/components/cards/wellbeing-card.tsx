"use client";

import { Activity, Heart, LifeBuoy, Phone, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import type { WellbeingReflection } from "@/lib/types";

function Resources({ reflection }: { reflection: WellbeingReflection }) {
  if (!reflection.resources.length) return null;
  return (
    <div className="space-y-2.5">
      {reflection.resources.map((r, i) => (
        <div
          key={i}
          className="rounded-[--radius-md] border border-border bg-card p-3.5"
        >
          <p className="flex items-center gap-2 text-sm font-medium">
            <LifeBuoy className="size-4 text-primary" />
            {r.name}
          </p>
          <p className="mt-1 flex items-center gap-1.5 text-sm">
            <Phone className="size-3.5 text-muted-foreground" />
            <span className="font-medium tracking-wide">{r.contact}</span>
          </p>
          <p className="mt-1 text-xs text-muted-foreground">{r.description}</p>
        </div>
      ))}
    </div>
  );
}

function Disclaimer({ text }: { text: string }) {
  return <p className="text-xs leading-relaxed text-muted-foreground">{text}</p>;
}

export function WellbeingCard({ reflection }: { reflection: WellbeingReflection }) {
  // Distress handoff: rendered distinctly and calmly, resources foregrounded, no analysis.
  if (reflection.tone_flag === "distress_handoff") {
    return (
      <Card className="animate-fade-in overflow-hidden border-primary/30">
        <div className="bg-primary/8 p-5">
          <div className="flex items-center gap-2.5">
            <div className="flex size-9 items-center justify-center rounded-full bg-primary/15 text-primary">
              <Heart className="size-5" />
            </div>
            <p className="font-medium">You don&apos;t have to carry this alone</p>
          </div>
          <p className="mt-3 leading-relaxed">{reflection.supportive_message}</p>
        </div>
        <div className="space-y-4 p-5">
          <div>
            <p className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              People who can help
            </p>
            <Resources reflection={reflection} />
          </div>
          <Disclaimer text={reflection.disclaimer} />
        </div>
      </Card>
    );
  }

  const elevated = reflection.tone_flag === "elevated_workload";

  return (
    <Card className="animate-fade-in overflow-hidden">
      <div className="flex items-center gap-2 border-b border-border p-5">
        <div className="flex size-9 items-center justify-center rounded-full bg-primary/12 text-primary">
          <Heart className="size-[18px]" />
        </div>
        <p className="text-sm font-medium">Workload reflection</p>
        {elevated && (
          <Badge variant="warning" className="ml-auto">
            <Activity className="size-3" />
            Elevated workload
          </Badge>
        )}
      </div>

      <div className="space-y-5 p-5">
        {reflection.observations.length > 0 && (
          <div className="rounded-[--radius-md] bg-muted/50 p-3.5">
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              What your logs show
            </p>
            <ul className="space-y-1">
              {reflection.observations.map((o, i) => (
                <li key={i} className="text-sm text-muted-foreground">
                  {o}
                </li>
              ))}
            </ul>
          </div>
        )}

        {reflection.supportive_message && (
          <p className="leading-relaxed">{reflection.supportive_message}</p>
        )}

        {reflection.practical_suggestions.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              A few small things that might help
            </p>
            <ul className="space-y-1.5">
              {reflection.practical_suggestions.map((s, i) => (
                <li key={i} className="flex gap-2 text-sm">
                  <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" />
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {reflection.resources.length > 0 && <Resources reflection={reflection} />}

        <div className="border-t border-border pt-3">
          <Disclaimer text={reflection.disclaimer} />
        </div>
      </div>
    </Card>
  );
}
