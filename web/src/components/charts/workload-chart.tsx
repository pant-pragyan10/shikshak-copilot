"use client";

import type { WorkloadEntry } from "@/lib/types";

/**
 * A tiny, dependency-free SVG chart of recent workload: energy (1-5) as a line,
 * classes + papers as faint bars. Hand-rolled to avoid a charting dependency (and
 * React-19 compat friction) for what is a simple visualisation.
 */
export function WorkloadChart({ entries }: { entries: WorkloadEntry[] }) {
  const data = [...entries]
    .sort((a, b) => a.entry_date.localeCompare(b.entry_date))
    .slice(-14);

  if (data.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-[--radius-md] border border-dashed border-border text-sm text-muted-foreground">
        No workload logged yet — add an entry to see trends.
      </div>
    );
  }

  const W = 640;
  const H = 180;
  const padX = 28;
  const padY = 22;
  const n = data.length;
  const maxLoad = Math.max(1, ...data.map((d) => d.classes_taken + Math.ceil(d.papers_graded / 10)));

  const x = (i: number) => padX + (i * (W - padX * 2)) / Math.max(1, n - 1);
  const yEnergy = (e: number) => padY + ((5 - e) / 4) * (H - padY * 2);
  const barH = (load: number) => (load / maxLoad) * (H - padY * 2);

  const linePath = data
    .map((d, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${yEnergy(d.self_reported_energy).toFixed(1)}`)
    .join(" ");

  const barW = Math.min(22, (W - padX * 2) / n / 1.6);

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-44 w-full min-w-[520px]" role="img" aria-label="Workload trend">
        {[1, 2, 3, 4, 5].map((g) => (
          <line
            key={g}
            x1={padX}
            x2={W - padX}
            y1={yEnergy(g)}
            y2={yEnergy(g)}
            stroke="var(--color-border)"
            strokeWidth="1"
            strokeDasharray={g === 3 ? "0" : "2 4"}
            opacity={g === 3 ? 0.6 : 0.4}
          />
        ))}

        {data.map((d, i) => {
          const load = d.classes_taken + Math.ceil(d.papers_graded / 10);
          const h = barH(load);
          return (
            <rect
              key={i}
              x={x(i) - barW / 2}
              y={H - padY - h}
              width={barW}
              height={h}
              rx={3}
              fill="var(--color-primary)"
              opacity={0.14}
            />
          );
        })}

        <path d={linePath} fill="none" stroke="var(--color-primary)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        {data.map((d, i) => (
          <circle key={i} cx={x(i)} cy={yEnergy(d.self_reported_energy)} r={3.5} fill="var(--color-primary)" />
        ))}
      </svg>
      <div className="mt-1 flex items-center gap-4 px-1 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded bg-primary" /> Energy (1–5)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm bg-primary/20" /> Load (classes + papers)
        </span>
      </div>
    </div>
  );
}
