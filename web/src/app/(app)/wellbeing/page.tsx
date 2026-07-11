"use client";

import * as React from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { HeartPulse, Send } from "lucide-react";
import { toast } from "sonner";
import { WellbeingCard } from "@/components/cards/wellbeing-card";
import { WorkloadChart } from "@/components/charts/workload-chart";
import { PageHeader } from "@/components/layout/page-header";
import { ToolShell } from "@/components/layout/tool-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { Spinner } from "@/components/ui/misc";
import { ApiError, api } from "@/lib/api";
import { useTeacher } from "@/lib/teacher";
import type { ChatResponse, WellbeingReflection } from "@/lib/types";

export default function WellbeingPage() {
  const { teacherId } = useTeacher();
  const [message, setMessage] = React.useState("");
  const [reflection, setReflection] = React.useState<WellbeingReflection | null>(null);
  const [fallback, setFallback] = React.useState<string | null>(null);

  const profileQuery = useQuery({
    queryKey: ["profile", teacherId],
    queryFn: () => api.getProfile(teacherId),
    retry: false,
  });

  const mutation = useMutation({
    mutationFn: (): Promise<ChatResponse> =>
      api.chat({ teacher_id: teacherId, message }),
    onSuccess: (res) => {
      if (res.agent_output && res.agent_output.type === "wellbeing") {
        setReflection(res.agent_output as unknown as WellbeingReflection);
        setFallback(null);
      } else {
        setReflection(null);
        setFallback(res.message);
      }
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : (e as Error).message),
  });

  const entries = profileQuery.data?.workload_log ?? [];

  const aside = (
    <div className="space-y-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        About this space
      </p>
      <p className="text-sm text-muted-foreground">
        This is a workload-awareness tool — not therapy or diagnosis. The patterns it reflects come
        from real numbers in your log, not from a model guessing.
      </p>
      <p className="text-sm text-muted-foreground">
        Log your day on the{" "}
        <a href="/profile" className="text-primary underline-offset-2 hover:underline">
          Profile
        </a>{" "}
        page so check-ins have something to reflect on.
      </p>
    </div>
  );

  return (
    <ToolShell aside={aside} asideTitle="Wellbeing">
      <div className="mx-auto w-full max-w-3xl px-5 py-8 sm:px-8">
        <PageHeader
          icon={HeartPulse}
          title="Wellbeing check-in"
          description="A caring colleague, not a clinician. It surfaces workload patterns from your own logs and responds with warmth — never a diagnosis."
        />

        <Card>
          <CardHeader>
            <CardTitle>Your recent workload</CardTitle>
          </CardHeader>
          <CardContent>
            <WorkloadChart entries={entries} />
          </CardContent>
        </Card>

        <Card className="mt-6 p-5">
          <label className="mb-2 block text-sm font-medium">How are you doing this week?</label>
          <Textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="e.g. I'm feeling really drained after back-to-back classes…"
            className="min-h-24"
          />
          <Button
            className="mt-3"
            disabled={!message.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? <Spinner /> : <Send className="size-4" />}
            {mutation.isPending ? "Reflecting…" : "Check in"}
          </Button>
        </Card>

        <div className="mt-6">
          {reflection && <WellbeingCard reflection={reflection} />}
          {fallback && !reflection && (
            <Card className="p-5 text-sm text-muted-foreground">{fallback}</Card>
          )}
        </div>
      </div>
    </ToolShell>
  );
}
