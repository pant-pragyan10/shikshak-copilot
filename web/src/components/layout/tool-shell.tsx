"use client";

import * as React from "react";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import { cn } from "@/lib/utils";

/** The right, contextual sidebar — collapsible, hidden on smaller screens. */
export function ContextSidebar({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(true);
  return (
    <div
      className={cn(
        "hidden lg:flex h-full shrink-0 flex-col border-l border-border bg-card/40 transition-[width] duration-300",
        open ? "w-80" : "w-12",
      )}
    >
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-border px-3">
        {open && (
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {title}
          </span>
        )}
        <button
          onClick={() => setOpen((o) => !o)}
          aria-label={open ? "Collapse panel" : "Open panel"}
          className={cn(
            "flex size-8 items-center justify-center rounded-[--radius-md] text-muted-foreground hover:bg-muted hover:text-foreground",
            !open && "mx-auto",
          )}
        >
          {open ? <PanelRightClose className="size-[18px]" /> : <PanelRightOpen className="size-[18px]" />}
        </button>
      </div>
      {open && <div className="flex-1 overflow-y-auto scrollbar-slim p-4">{children}</div>}
    </div>
  );
}

/** Main work area + optional contextual right sidebar. */
export function ToolShell({
  children,
  aside,
  asideTitle = "Context",
}: {
  children: React.ReactNode;
  aside?: React.ReactNode;
  asideTitle?: string;
}) {
  return (
    <div className="flex h-full min-h-0">
      <div className="flex-1 min-w-0 overflow-y-auto scrollbar-slim">{children}</div>
      {aside ? <ContextSidebar title={asideTitle}>{aside}</ContextSidebar> : null}
    </div>
  );
}
