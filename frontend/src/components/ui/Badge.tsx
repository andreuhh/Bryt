import type { ReactNode } from "react";

type Tone = "neutral" | "pace" | "load" | "nutrition" | "outline";

const tones: Record<Tone, string> = {
  neutral: "bg-elevated text-fg-muted",
  pace: "bg-accent-pace/15 text-accent-pace",
  load: "bg-accent-load/15 text-accent-load",
  nutrition: "bg-accent-nutrition/15 text-accent-nutrition",
  outline: "border border-line-strong text-fg-subtle",
};

export function Badge({
  tone = "neutral",
  children,
  className = "",
  title,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-pill px-2.5 py-0.5 text-xs font-medium ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
