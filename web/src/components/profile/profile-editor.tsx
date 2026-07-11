"use client";

import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, Save } from "lucide-react";
import { toast } from "sonner";
import { WorkloadChart } from "@/components/charts/workload-chart";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { Spinner } from "@/components/ui/misc";
import { ApiError, api } from "@/lib/api";
import { BOARDS, SUBJECTS } from "@/lib/constants";
import type { Board, TeacherProfile, WorkloadEntry } from "@/lib/types";
import { cn } from "@/lib/utils";

const GRADES = ["5", "6", "7", "8", "9", "10", "11", "12"];

function Chips({
  options,
  value,
  onChange,
}: {
  options: string[];
  value: string[];
  onChange: (v: string[]) => void;
}) {
  const toggle = (o: string) =>
    onChange(value.includes(o) ? value.filter((x) => x !== o) : [...value, o]);
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button
          key={o}
          type="button"
          onClick={() => toggle(o)}
          className={cn(
            "rounded-full border px-3 py-1 text-sm transition-colors",
            value.includes(o)
              ? "border-primary bg-primary/12 text-primary"
              : "border-border text-muted-foreground hover:bg-muted",
          )}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

/**
 * The editable profile form. State is initialised once from `initial` (via lazy
 * useState), so there's no query→state sync effect. The page remounts this via a
 * `key` when the teacher id changes, which re-seeds the form cleanly.
 */
export function ProfileEditor({
  teacherId,
  initial,
}: {
  teacherId: string;
  initial: TeacherProfile | null;
}) {
  const qc = useQueryClient();

  const [form, setForm] = React.useState(() => ({
    name: initial?.name ?? "",
    subjects: initial?.subjects ?? ["Science"],
    grades_taught: initial?.grades_taught ?? ["8"],
    board: (initial?.board ?? "CBSE") as Board,
    years_experience: initial?.years_experience ?? 0,
  }));
  const [workloadLog, setWorkloadLog] = React.useState<WorkloadEntry[]>(
    () => initial?.workload_log ?? [],
  );
  const [entry, setEntry] = React.useState<WorkloadEntry>(() => ({
    entry_date: new Date().toISOString().slice(0, 10),
    papers_graded: 0,
    classes_taken: 0,
    self_reported_energy: 3,
  }));

  const save = useMutation({
    mutationFn: () =>
      api.putProfile(teacherId, {
        name: form.name || teacherId,
        subjects: form.subjects,
        grades_taught: form.grades_taught,
        board: form.board,
        years_experience: form.years_experience,
        workload_log: workloadLog,
      }),
    onSuccess: (p) => {
      qc.setQueryData(["profile", teacherId], p);
      toast.success("Profile saved.");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : (e as Error).message),
  });

  const logWorkload = useMutation({
    mutationFn: () => api.addWorkload(teacherId, entry),
    onSuccess: (p) => {
      qc.setQueryData(["profile", teacherId], p);
      setWorkloadLog(p.workload_log);
      toast.success("Workload logged.");
    },
    onError: (e) =>
      toast.error(
        e instanceof ApiError && e.status === 404
          ? "Save your profile first, then log workload."
          : e instanceof ApiError
            ? e.message
            : (e as Error).message,
      ),
  });

  return (
    <div className="space-y-6">
      <Card className="p-5">
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Your name"
              />
            </div>
            <div>
              <Label htmlFor="years">Years of experience</Label>
              <Input
                id="years"
                type="number"
                min={0}
                value={form.years_experience}
                onChange={(e) => setForm({ ...form, years_experience: Number(e.target.value) })}
              />
            </div>
          </div>
          <div>
            <Label>Subjects</Label>
            <Chips
              options={Array.from(new Set([...SUBJECTS, ...form.subjects]))}
              value={form.subjects}
              onChange={(v) => setForm({ ...form, subjects: v })}
            />
          </div>
          <div>
            <Label>Grades taught</Label>
            <Chips
              options={GRADES}
              value={form.grades_taught}
              onChange={(v) => setForm({ ...form, grades_taught: v })}
            />
          </div>
          <div className="max-w-[200px]">
            <Label htmlFor="board">Board</Label>
            <Select
              id="board"
              value={form.board}
              onChange={(e) => setForm({ ...form, board: e.target.value as Board })}
            >
              {BOARDS.map((b) => (
                <option key={b}>{b}</option>
              ))}
            </Select>
          </div>
          <Button onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? <Spinner /> : <Save className="size-4" />}
            Save profile
          </Button>
        </div>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Log today&apos;s workload</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <WorkloadChart entries={workloadLog} />
          <div className="grid gap-3 sm:grid-cols-4">
            <div>
              <Label htmlFor="date">Date</Label>
              <Input
                id="date"
                type="date"
                value={entry.entry_date}
                onChange={(e) => setEntry({ ...entry, entry_date: e.target.value })}
              />
            </div>
            <div>
              <Label htmlFor="papers">Papers</Label>
              <Input
                id="papers"
                type="number"
                min={0}
                value={entry.papers_graded}
                onChange={(e) => setEntry({ ...entry, papers_graded: Number(e.target.value) })}
              />
            </div>
            <div>
              <Label htmlFor="classes">Classes</Label>
              <Input
                id="classes"
                type="number"
                min={0}
                value={entry.classes_taken}
                onChange={(e) => setEntry({ ...entry, classes_taken: Number(e.target.value) })}
              />
            </div>
            <div>
              <Label htmlFor="energy">Energy (1–5)</Label>
              <Select
                id="energy"
                value={String(entry.self_reported_energy)}
                onChange={(e) => setEntry({ ...entry, self_reported_energy: Number(e.target.value) })}
              >
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <Button
            variant="secondary"
            onClick={() => logWorkload.mutate()}
            disabled={logWorkload.isPending}
          >
            {logWorkload.isPending ? <Spinner /> : <CalendarPlus className="size-4" />}
            Log workload
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
