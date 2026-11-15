import type { HTMLAttributes } from "react";

type CardProps = HTMLAttributes<HTMLDivElement> & {
  /** "container" = main bento cell (rounded-3xl), "card" = nested card (rounded-2xl). */
  variant?: "container" | "card";
};

export function Card({ variant = "container", className = "", ...props }: CardProps) {
  const radius = variant === "container" ? "rounded-container p-6" : "rounded-card p-4";
  return <div className={`bg-surface border border-line ${radius} ${className}`} {...props} />;
}
