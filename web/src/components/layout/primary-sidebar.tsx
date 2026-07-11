"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { LogoMark, Wordmark } from "@/components/brand/logo";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Tooltip } from "@/components/ui/tooltip";
import { MODES } from "@/lib/constants";
import { useTeacher } from "@/lib/teacher";
import { cn } from "@/lib/utils";

export function PrimarySidebar() {
  const pathname = usePathname();
  const { teacherId } = useTeacher();
  const [collapsed, setCollapsed] = React.useState(false);

  return (
    <aside
      className={cn(
        "hidden md:flex h-dvh shrink-0 flex-col border-r border-border bg-card/60 backdrop-blur transition-[width] duration-300",
        collapsed ? "w-[68px]" : "w-64",
      )}
    >
      <div className="flex h-16 items-center justify-between px-3">
        {collapsed ? (
          <Link href="/chat" className="mx-auto">
            <LogoMark />
          </Link>
        ) : (
          <Link href="/chat" className="pl-1">
            <Wordmark />
          </Link>
        )}
      </div>

      <nav className="flex-1 space-y-1 px-3 py-2">
        {MODES.map((mode) => {
          const active = pathname.startsWith(mode.href);
          const Icon = mode.icon;
          const link = (
            <Link
              key={mode.href}
              href={mode.href}
              className={cn(
                "group flex items-center gap-3 rounded-[--radius-md] px-3 py-2.5 text-sm font-medium transition-colors",
                active
                  ? "bg-primary/12 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
                collapsed && "justify-center px-0",
              )}
            >
              <Icon className="size-[18px] shrink-0" />
              {!collapsed && <span>{mode.label}</span>}
            </Link>
          );
          return collapsed ? (
            <Tooltip key={mode.href} content={mode.label} side="right">
              {link}
            </Tooltip>
          ) : (
            link
          );
        })}
      </nav>

      <div className={cn("border-t border-border p-3", collapsed && "flex flex-col items-center gap-2")}>
        {!collapsed && (
          <div className="mb-2 rounded-[--radius-md] bg-muted px-3 py-2">
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Signed in as</p>
            <p className="truncate text-sm font-medium">{teacherId}</p>
          </div>
        )}
        <div className={cn("flex items-center", collapsed ? "flex-col gap-1" : "justify-between")}>
          <ThemeToggle />
          <button
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="flex size-9 items-center justify-center rounded-[--radius-md] text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {collapsed ? <PanelLeftOpen className="size-[18px]" /> : <PanelLeftClose className="size-[18px]" />}
          </button>
        </div>
      </div>
    </aside>
  );
}

export function MobileTopNav() {
  const pathname = usePathname();
  return (
    <div className="md:hidden sticky top-0 z-30 border-b border-border bg-card/80 backdrop-blur">
      <div className="flex h-14 items-center justify-between px-4">
        <Link href="/chat">
          <Wordmark markClassName="size-7" className="text-[17px]" />
        </Link>
        <ThemeToggle />
      </div>
      <nav className="flex gap-1 overflow-x-auto px-3 pb-2 scrollbar-slim">
        {MODES.map((mode) => {
          const active = pathname.startsWith(mode.href);
          const Icon = mode.icon;
          return (
            <Link
              key={mode.href}
              href={mode.href}
              className={cn(
                "flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium",
                active ? "bg-primary/12 text-primary" : "text-muted-foreground hover:bg-muted",
              )}
            >
              <Icon className="size-4" />
              {mode.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
