"use client";

import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { RubricCriterion } from "@/lib/types";

export function RubricBuilder({
  enabled,
  onToggle,
  criteria,
  onChange,
}: {
  enabled: boolean;
  onToggle: (v: boolean) => void;
  criteria: RubricCriterion[];
  onChange: (c: RubricCriterion[]) => void;
}) {
  const update = (i: number, patch: Partial<RubricCriterion>) =>
    onChange(criteria.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const add = () => onChange([...criteria, { name: "", description: "", max_marks: 2 }]);
  const remove = (i: number) => onChange(criteria.filter((_, j) => j !== i));

  const total = criteria.reduce((sum, c) => sum + (Number(c.max_marks) || 0), 0);

  return (
    <div className="rounded-[--radius-md] border border-border p-4">
      <label className="flex cursor-pointer items-center justify-between">
        <div>
          <p className="text-sm font-medium">Custom rubric</p>
          <p className="text-xs text-muted-foreground">
            Off = the AI generates a rubric and shows it to you.
          </p>
        </div>
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => onToggle(e.target.checked)}
          className="size-4 accent-[var(--color-primary)]"
        />
      </label>

      {enabled && (
        <div className="mt-4 space-y-2.5">
          {criteria.map((c, i) => (
            <div key={i} className="flex items-start gap-2">
              <Input
                placeholder="Criterion (e.g. Accuracy)"
                value={c.name}
                onChange={(e) => update(i, { name: e.target.value })}
                className="flex-1"
              />
              <Input
                type="number"
                min={1}
                value={c.max_marks}
                onChange={(e) => update(i, { max_marks: Number(e.target.value) })}
                className="w-20"
                aria-label="Max marks"
              />
              <Button variant="ghost" size="icon" onClick={() => remove(i)} aria-label="Remove criterion">
                <Trash2 className="size-4" />
              </Button>
            </div>
          ))}
          <div className="flex items-center justify-between pt-1">
            <Button variant="outline" size="sm" onClick={add}>
              <Plus className="size-4" />
              Add criterion
            </Button>
            <span className="text-sm text-muted-foreground">Total: {total} marks</span>
          </div>
        </div>
      )}
    </div>
  );
}
