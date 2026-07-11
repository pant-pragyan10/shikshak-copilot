"use client";

import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { Compass, Send } from "lucide-react";
import { toast } from "sonner";
import { CareerCard } from "@/components/cards/career-card";
import { PageHeader } from "@/components/layout/page-header";
import { ToolShell } from "@/components/layout/tool-shell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { Skeleton, Spinner } from "@/components/ui/misc";
import { ApiError, api } from "@/lib/api";
import { useTeacher } from "@/lib/teacher";
import type { CareerGuidance } from "@/lib/types";

const PROMPTS = [
  "I'm curious about moving into edtech content roles.",
  "How could I transition into instructional design?",
  "I enjoy setting papers — what could that lead to?",
  "I want more growth without leaving the classroom.",
];

export default function CareerPage() {
  const { teacherId } = useTeacher();
  const [interest, setInterest] = React.useState("");
  const [guidance, setGuidance] = React.useState<CareerGuidance | null>(null);

  const mutation = useMutation({
    mutationFn: () => api.career({ interest, teacher_id: teacherId }),
    onSuccess: setGuidance,
    onError: (e) => toast.error(e instanceof ApiError ? e.message : (e as Error).message),
  });

  const aside = (
    <div className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Try asking</p>
      {PROMPTS.map((p) => (
        <button
          key={p}
          onClick={() => setInterest(p)}
          className="w-full rounded-[--radius-md] border border-border bg-card p-3 text-left text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
        >
          {p}
        </button>
      ))}
    </div>
  );

  return (
    <ToolShell aside={aside} asideTitle="Ideas">
      <div className="mx-auto w-full max-w-3xl px-5 py-8 sm:px-8">
        <PageHeader
          icon={Compass}
          title="Career guidance"
          description="Grounded, honest directions for teachers in India — matched to a curated set of paths, with real tradeoffs and no invented salaries."
        />

        <Card className="p-5">
          <label className="mb-2 block text-sm font-medium">
            What are you curious about, or where are you now?
          </label>
          <Textarea
            value={interest}
            onChange={(e) => setInterest(e.target.value)}
            placeholder="e.g. I've taught Science for 6 years and want to explore edtech…"
            className="min-h-24"
          />
          <Button
            className="mt-3"
            disabled={!interest.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? <Spinner /> : <Send className="size-4" />}
            {mutation.isPending ? "Thinking…" : "Get guidance"}
          </Button>
        </Card>

        <div className="mt-6">
          {mutation.isPending && (
            <Card className="space-y-3 p-5">
              <Skeleton className="h-5 w-1/2" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
            </Card>
          )}
          {guidance && !mutation.isPending && <CareerCard guidance={guidance} />}
        </div>
      </div>
    </ToolShell>
  );
}
