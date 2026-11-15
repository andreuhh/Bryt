import type { ButtonHTMLAttributes } from "react";

type PillProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  active?: boolean;
};

export function Pill({ active = false, className = "", ...props }: PillProps) {
  const state = active
    ? "bg-fg text-canvas"
    : "bg-elevated text-fg-muted hover:bg-elevated-hover hover:text-fg";
  return (
    <button
      type="button"
      className={`rounded-pill px-4 py-2 text-sm font-medium transition-colors ${state} ${className}`}
      {...props}
    />
  );
}
