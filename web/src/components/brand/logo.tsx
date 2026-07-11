import { cn } from "@/lib/utils";

/** A simple, owned SVG mark: a "learning spark" tile — sparkle over a page line. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-8", className)} aria-hidden="true">
      <rect width="32" height="32" rx="9" className="fill-primary" />
      {/* 4-point sparkle (the copilot signifier) */}
      <path
        d="M16 6.5c.7 4.6 2.2 6.1 6.8 6.8-4.6.7-6.1 2.2-6.8 6.8-.7-4.6-2.2-6.1-6.8-6.8 4.6-.7 6.1-2.2 6.8-6.8Z"
        className="fill-primary-foreground"
      />
      {/* page / desk line */}
      <rect x="9.5" y="23.5" width="13" height="2.2" rx="1.1" className="fill-primary-foreground/70" />
    </svg>
  );
}

export function Wordmark({ className, markClassName }: { className?: string; markClassName?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <LogoMark className={markClassName} />
      <span className="font-display text-[19px] font-medium leading-none tracking-tight">
        Teacher<span className="text-primary">Copilot</span>
      </span>
    </span>
  );
}
