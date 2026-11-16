"use client";

import { Button } from "@/components/ui/Button";
import { formatDay } from "@/lib/format";
import { workoutVolume } from "@/lib/plan";
import { useResolveProposal } from "@/lib/queries";
import type { WorkoutRevision } from "@/lib/types";

/** Key-session changes proposed by the weekly refinement: never applied without consent. */
export function Proposals({ proposals }: { proposals: WorkoutRevision[] }) {
  const resolve = useResolveProposal();
  if (!proposals.length) return null;

  return (
    <section className="flex flex-col gap-3 rounded-container border border-accent-pace/30 bg-accent-pace/5 p-5">
      <div>
        <h2 className="font-semibold">Modifiche proposte alle sessioni chiave</h2>
        <p className="text-sm text-fg-muted">Il coach suggerisce questi cambi. Si applicano solo se li accetti.</p>
      </div>
      {proposals.map((p) => {
        const busy = resolve.isPending && resolve.variables?.id === p.id;
        return (
          <article key={p.id} className="flex flex-col gap-3 rounded-card bg-surface p-4">
            <div className="grid gap-2 text-sm sm:grid-cols-2">
              <div>
                <p className="text-xs uppercase tracking-wider text-fg-subtle">Ora</p>
                <p className="text-fg-muted line-through decoration-fg-subtle">{p.before?.title}</p>
                {p.before && (
                  <p className="text-xs text-fg-subtle first-letter:uppercase">
                    {formatDay(p.before.scheduled_date)} · {workoutVolume(p.before)}
                  </p>
                )}
              </div>
              <div>
                <p className="text-xs uppercase tracking-wider text-fg-subtle">Proposta</p>
                <p className="font-medium">{p.after.title}</p>
                <p className="text-xs text-fg-muted first-letter:uppercase">
                  {formatDay(p.after.scheduled_date)} · {workoutVolume(p.after)}
                </p>
              </div>
            </div>
            <p className="text-sm text-fg-muted">{p.reason}</p>
            <div className="flex gap-2">
              <Button size="sm" loading={busy} onClick={() => resolve.mutate({ id: p.id, accept: true })}>
                Accetta
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() => resolve.mutate({ id: p.id, accept: false })}
              >
                Rifiuta
              </Button>
            </div>
          </article>
        );
      })}
    </section>
  );
}
