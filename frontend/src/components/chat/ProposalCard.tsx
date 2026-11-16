"use client";

import Link from "next/link";

import { IconCalendar } from "@/components/icons";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/States";
import { adjustErrorMessage, type ChatTurn } from "@/lib/chat";
import { formatShort } from "@/lib/format";
import { WORKOUT_LABEL, workoutVolume } from "@/lib/plan";
import { useApplyAdjustment } from "@/lib/queries";
import type { PlanAdjustment } from "@/lib/types";

/** A plan change proposed by the coach: never applied until the athlete confirms it. */
export function ProposalCard({
  proposal,
  outcome,
  onOutcome,
}: {
  proposal: PlanAdjustment;
  outcome: ChatTurn["outcome"];
  onOutcome: (outcome: NonNullable<ChatTurn["outcome"]>) => void;
}) {
  const apply = useApplyAdjustment();
  const days = proposal.days_affected === 1 ? "il prossimo giorno" : `i prossimi ${proposal.days_affected} giorni`;

  if (outcome && outcome !== "dismissed") {
    const { modified, rationale } = outcome.applied;
    return (
      <div className="flex flex-col gap-3 rounded-card border border-line bg-surface p-4">
        <div className="flex items-center gap-2">
          <Badge tone="pace">Piano aggiornato</Badge>
          <span className="text-xs text-fg-subtle">{modified.length} sessioni modificate</span>
        </div>
        <p className="text-sm text-fg-muted">{rationale}</p>
        <ul className="flex flex-col divide-y divide-line">
          {modified.map((w) => (
            <li key={w.id} className="flex items-baseline justify-between gap-3 py-2 text-sm">
              <span className="min-w-0">
                <span className="metric text-fg-subtle first-letter:uppercase">{formatShort(w.scheduled_date)}</span>{" "}
                <span className="text-fg">{w.title}</span>
              </span>
              <span className="metric shrink-0 text-fg-muted">{workoutVolume(w) ?? WORKOUT_LABEL[w.workout_type]}</span>
            </li>
          ))}
        </ul>
        <Link href="/plan" className="self-start text-sm text-fg-muted underline-offset-4 hover:text-fg hover:underline">
          Vedi nel piano
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 rounded-card border border-line-strong bg-surface p-4">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-fg-subtle">
        <IconCalendar className="size-4" />
        Proposta di modifica · {days}
      </div>
      <p className="text-sm font-medium text-fg">{proposal.reason}</p>
      <p className="text-sm text-fg-muted">{proposal.guidance}</p>
      {outcome === "dismissed" ? (
        <p className="text-xs text-fg-subtle">Non applicata. Il piano resta com&apos;è.</p>
      ) : (
        <>
          {apply.isError && <ErrorState message={adjustErrorMessage(apply.error)} />}
          {apply.isPending && (
            <p className="text-xs text-fg-subtle" aria-live="polite">
              Il coach sta riscrivendo i prossimi giorni: di solito meno di un minuto.
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              loading={apply.isPending}
              onClick={() => apply.mutate(proposal, { onSuccess: (applied) => onOutcome({ applied }) })}
            >
              Applica al piano
            </Button>
            <Button size="sm" variant="ghost" disabled={apply.isPending} onClick={() => onOutcome("dismissed")}>
              Non ora
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
