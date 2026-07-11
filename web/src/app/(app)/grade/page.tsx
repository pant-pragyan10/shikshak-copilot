"use client";

import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { FileText, ImageUp, PenLine } from "lucide-react";
import { toast } from "sonner";
import { GradedResultCard } from "@/components/cards/graded-result-card";
import { ImageDrop } from "@/components/grade/image-drop";
import { RubricBuilder } from "@/components/grade/rubric-builder";
import { PageHeader } from "@/components/layout/page-header";
import { ToolShell } from "@/components/layout/tool-shell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label, Textarea } from "@/components/ui/input";
import { Skeleton, Spinner } from "@/components/ui/misc";
import { ApiError, api } from "@/lib/api";
import { useTeacher } from "@/lib/teacher";
import type { GradedResult, Rubric, RubricCriterion } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function GradePage() {
  const { teacherId } = useTeacher();
  const [mode, setMode] = React.useState<"text" | "image">("text");
  const [question, setQuestion] = React.useState("");
  const [answerText, setAnswerText] = React.useState("");
  const [imageFile, setImageFile] = React.useState<File | null>(null);
  const [useRubric, setUseRubric] = React.useState(false);
  const [criteria, setCriteria] = React.useState<RubricCriterion[]>([
    { name: "Accuracy", description: "", max_marks: 3 },
    { name: "Clarity", description: "", max_marks: 2 },
  ]);
  const [result, setResult] = React.useState<GradedResult | null>(null);

  const rubric: Rubric | null =
    useRubric && criteria.some((c) => c.name.trim())
      ? { criteria: criteria.filter((c) => c.name.trim()) }
      : null;

  const mutation = useMutation({
    mutationFn: async (): Promise<GradedResult> => {
      if (mode === "image") {
        if (!imageFile) throw new Error("Add an answer image first.");
        return api.gradeImage({
          file: imageFile,
          question,
          rubricJson: rubric ? JSON.stringify(rubric) : undefined,
          teacherId,
        });
      }
      return api.grade({ question, answer_text: answerText, rubric, teacher_id: teacherId });
    },
    onSuccess: setResult,
    onError: (e) => toast.error(e instanceof ApiError ? e.message : (e as Error).message),
  });

  const canSubmit = Boolean(question.trim()) && (mode === "text" ? Boolean(answerText.trim()) : Boolean(imageFile));

  const activeRubric = result?.rubric ?? rubric;
  const aside = (
    <div className="space-y-4">
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Rubric in use
        </p>
        {activeRubric ? (
          <div className="space-y-2">
            {activeRubric.criteria.map((c, i) => (
              <div key={i} className="flex items-center justify-between rounded-[--radius-md] border border-border bg-card px-3 py-2 text-sm">
                <span className="truncate">{c.name}</span>
                <span className="shrink-0 text-muted-foreground">{c.max_marks}</span>
              </div>
            ))}
            {result?.rubric_source === "auto" && (
              <p className="text-xs text-muted-foreground">Auto-generated for this question.</p>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No rubric yet — the AI will generate one from your question and show it here.
          </p>
        )}
      </div>
    </div>
  );

  return (
    <ToolShell aside={aside} asideTitle="Grading context">
      <div className="mx-auto w-full max-w-3xl px-5 py-8 sm:px-8">
        <PageHeader
          icon={PenLine}
          title="Grade an answer"
          description="An explicit tool — no guessing from phrasing. Grade a typed answer, or upload a scanned answer sheet for the vision path."
        />

        <Card className="p-5">
          <div className="mb-4 inline-flex rounded-[--radius-md] bg-muted p-1">
            {(["text", "image"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={cn(
                  "flex items-center gap-1.5 rounded-[--radius-sm] px-3 py-1.5 text-sm font-medium transition-colors",
                  mode === m ? "bg-card text-foreground shadow-sm" : "text-muted-foreground",
                )}
              >
                {m === "text" ? <FileText className="size-4" /> : <ImageUp className="size-4" />}
                {m === "text" ? "Typed answer" : "Scanned image"}
              </button>
            ))}
          </div>

          <div className="space-y-4">
            <div>
              <Label htmlFor="q">Question</Label>
              <Textarea
                id="q"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="e.g. State Newton's second law of motion and give its formula."
                className="min-h-16"
              />
            </div>

            {mode === "text" ? (
              <div>
                <Label htmlFor="a">Student&apos;s answer</Label>
                <Textarea
                  id="a"
                  value={answerText}
                  onChange={(e) => setAnswerText(e.target.value)}
                  placeholder="Paste or type the student's answer…"
                  className="min-h-32"
                />
              </div>
            ) : (
              <div>
                <Label>Answer sheet</Label>
                <ImageDrop file={imageFile} onFile={setImageFile} />
              </div>
            )}

            <RubricBuilder
              enabled={useRubric}
              onToggle={setUseRubric}
              criteria={criteria}
              onChange={setCriteria}
            />

            <Button
              size="lg"
              className="w-full"
              disabled={!canSubmit || mutation.isPending}
              onClick={() => mutation.mutate()}
            >
              {mutation.isPending ? <Spinner /> : null}
              {mutation.isPending ? "Grading…" : "Grade answer"}
            </Button>
          </div>
        </Card>

        <div className="mt-6">
          {mutation.isPending && (
            <Card className="p-5">
              <div className="flex items-center gap-4">
                <Skeleton className="size-24 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-5 w-40" />
                  <Skeleton className="h-4 w-full" />
                </div>
              </div>
            </Card>
          )}
          {result && !mutation.isPending && (
            <>
              <Label className="mb-2">Result</Label>
              <GradedResultCard result={result} />
            </>
          )}
        </div>
      </div>
    </ToolShell>
  );
}
