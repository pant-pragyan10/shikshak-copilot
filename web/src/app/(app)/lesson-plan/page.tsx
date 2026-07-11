"use client";

import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { BookOpen, FileText } from "lucide-react";
import { toast } from "sonner";
import { LessonPlanCard } from "@/components/cards/lesson-plan-card";
import { PageHeader } from "@/components/layout/page-header";
import { ToolShell } from "@/components/layout/tool-shell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { Skeleton, Spinner } from "@/components/ui/misc";
import { ApiError, api } from "@/lib/api";
import { BOARDS, SUBJECTS } from "@/lib/constants";
import type { Board, LessonPlan } from "@/lib/types";

export default function LessonPlanPage() {
  const [topic, setTopic] = React.useState("");
  const [subject, setSubject] = React.useState("Science");
  const [grade, setGrade] = React.useState("8");
  const [board, setBoard] = React.useState<Board>("CBSE");
  const [duration, setDuration] = React.useState(40);
  const [notes, setNotes] = React.useState("");
  const [plan, setPlan] = React.useState<LessonPlan | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      api.lessonPlan({
        topic,
        subject,
        grade,
        board,
        duration_minutes: duration,
        notes: notes.trim() || null,
      }),
    onSuccess: setPlan,
    onError: (e) => toast.error(e instanceof ApiError ? e.message : (e as Error).message),
  });

  const aside = (
    <div className="space-y-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Citations</p>
      {plan && plan.citations.length > 0 ? (
        <div className="space-y-2.5">
          {plan.citations.map((c, i) => (
            <div key={i} className="rounded-[--radius-md] border border-border bg-card p-3">
              <p className="flex items-center gap-1.5 text-sm font-medium">
                <FileText className="size-3.5 text-primary" />
                {c.source}
              </p>
              <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">{c.snippet}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          When the plan is grounded in your ingested curriculum, the source excerpts appear here.
        </p>
      )}
    </div>
  );

  return (
    <ToolShell aside={aside} asideTitle="Curriculum sources">
      <div className="mx-auto w-full max-w-3xl px-5 py-8 sm:px-8">
        <PageHeader
          icon={BookOpen}
          title="Lesson plan"
          description="Curriculum-grounded, cited, and honest about it — plans say when they're backed by real syllabus and when they're not."
        />

        <Card className="p-5">
          <div className="space-y-4">
            <div>
              <Label htmlFor="topic">Topic</Label>
              <Input
                id="topic"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="e.g. Reflection of light"
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label htmlFor="subject">Subject</Label>
                <Select id="subject" value={subject} onChange={(e) => setSubject(e.target.value)}>
                  {SUBJECTS.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="grade">Class / Grade</Label>
                <Select id="grade" value={grade} onChange={(e) => setGrade(e.target.value)}>
                  {["5", "6", "7", "8", "9", "10", "11", "12"].map((g) => (
                    <option key={g}>{g}</option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="board">Board</Label>
                <Select id="board" value={board} onChange={(e) => setBoard(e.target.value as Board)}>
                  {BOARDS.map((b) => (
                    <option key={b}>{b}</option>
                  ))}
                </Select>
              </div>
              <div>
                <Label htmlFor="duration">Duration (minutes)</Label>
                <Input
                  id="duration"
                  type="number"
                  min={10}
                  max={180}
                  value={duration}
                  onChange={(e) => setDuration(Number(e.target.value))}
                />
              </div>
            </div>
            <div>
              <Label htmlFor="notes">Notes (optional)</Label>
              <Textarea
                id="notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Any constraints — e.g. no lab available, mixed-ability class…"
                className="min-h-16"
              />
            </div>
            <Button
              size="lg"
              className="w-full"
              disabled={!topic.trim() || mutation.isPending}
              onClick={() => mutation.mutate()}
            >
              {mutation.isPending ? <Spinner /> : null}
              {mutation.isPending ? "Planning…" : "Generate lesson plan"}
            </Button>
          </div>
        </Card>

        <div className="mt-6">
          {mutation.isPending && (
            <Card className="space-y-3 p-5">
              <Skeleton className="h-6 w-2/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-24 w-full" />
            </Card>
          )}
          {plan && !mutation.isPending && <LessonPlanCard plan={plan} />}
        </div>
      </div>
    </ToolShell>
  );
}
