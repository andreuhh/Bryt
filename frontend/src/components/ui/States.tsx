import type { ReactNode } from "react";

import { IconAlert } from "@/components/icons";

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-card bg-elevated ${className}`} />;
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-container border border-dashed border-line-strong px-6 py-12 text-center">
      <p className="font-display text-lg font-semibold">{title}</p>
      {description && <p className="max-w-md text-sm text-fg-muted">{description}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-card border border-accent-load/30 bg-accent-load/10 p-4 text-sm">
      <IconAlert className="mt-0.5 shrink-0 text-accent-load" />
      <div className="flex-1">
        <p className="font-medium text-fg">Qualcosa non ha funzionato</p>
        <p className="text-fg-muted">{message}</p>
      </div>
      {onRetry && (
        <button type="button" onClick={onRetry} className="text-accent-load underline-offset-4 hover:underline">
          Riprova
        </button>
      )}
    </div>
  );
}
