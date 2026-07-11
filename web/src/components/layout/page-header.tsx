import * as React from "react";
import type { LucideIcon } from "lucide-react";

export function PageHeader({
  icon: Icon,
  title,
  description,
  actions,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="flex items-start gap-3">
        {Icon && (
          <div className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-[--radius-md] bg-primary/12 text-primary">
            <Icon className="size-5" />
          </div>
        )}
        <div>
          <h1 className="font-display text-2xl font-medium tracking-tight text-balance">{title}</h1>
          {description && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>}
        </div>
      </div>
      {actions}
    </div>
  );
}

/** Standard padded container for form-style tool pages. */
export function PagePad({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`mx-auto w-full max-w-4xl px-5 py-8 sm:px-8 ${className}`}>{children}</div>;
}
