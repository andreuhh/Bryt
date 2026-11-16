"use client";

import { useState } from "react";

import { IconRefresh } from "@/components/icons";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ErrorState } from "@/components/ui/States";
import { daysBetween, formatLong } from "@/lib/format";
import { useRefinePlan } from "@/lib/queries";
import type { TrainingPlan } from "@/lib/types";

const METHODOLOGY: Record<TrainingPlan["methodology"], string> = {
  DOUBLE_THRESHOLD: "Doppia soglia",
  BLOCK: "A blocchi",
  TRADITIONAL: "Tradizionale",
};

export function PlanHeader({ plan, today }: { plan: TrainingPlan; today: string }) {
  const daysToRace = daysBetween(today, plan.end_date);
  const [showWhy, setShowWhy] = useState(false);

  return (
    <header className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
      <div className="flex max-w-3xl flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="pace">{METHODOLOGY[plan.methodology]}</Badge>
          {plan.last_refined_on && <Badge>Aggiornato il {formatLong(plan.last_refined_on)}</Badge>}
        </div>
        <h1 className="text-3xl font-bold sm:text-4xl">{plan.name}</h1>
        {plan.goal_summary && <p className="text-sm leading-relaxed text-fg-muted">{plan.goal_summary}</p>}
        {plan.rationale && (
          <div>
            <button
              type="button"
              onClick={() => setShowWhy((v) => !v)}
              className="text-sm text-fg underline decoration-line-strong underline-offset-4 hover:decoration-fg"
            >
              {showWhy ? "Nascondi il ragionamento" : "Perché questo piano"}
            </button>
            {showWhy && <p className="mt-3 text-sm leading-relaxed text-fg-muted">{plan.rationale}</p>}
          </div>
        )}
      </div>
      <div className="flex items-end gap-6">
        <div className="text-right">
          <p className="text-xs uppercase tracking-wider text-fg-subtle">Al via</p>
          <p className="font-display text-5xl font-bold leading-none">{Math.max(daysToRace, 0)}</p>
          <p className="text-xs text-fg-muted">giorni · {formatLong(plan.end_date)}</p>
        </div>
        <RefineButton />
      </div>
    </header>
  );
}

function RefineButton() {
  const [open, setOpen] = useState(false);
  const refine = useRefinePlan();

  return (
    <>
      <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>
        <IconRefresh width={16} height={16} />
        Aggiorna ora
      </Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Aggiorna il piano">
        <div className="flex flex-col gap-4 text-sm">
          {refine.isSuccess ? (
            <>
              <p>
                {refine.data.confirmed.length
                  ? `Confermate ${refine.data.confirmed.length} sessioni delle prossime due settimane.`
                  : "Le prossime due settimane erano già confermate: nessuna modifica."}
              </p>
              {refine.data.notes && <p className="text-fg-muted">{refine.data.notes}</p>}
              {refine.data.proposals.length > 0 && (
                <p className="text-fg-muted">
                  {refine.data.proposals.length} proposte sulle sessioni chiave ti aspettano in cima al piano.
                </p>
              )}
              <Button onClick={() => setOpen(false)}>Chiudi</Button>
            </>
          ) : (
            <>
              <p className="text-fg-muted">
                Avviene in automatico ogni domenica sera: il coach conferma le prossime due settimane con le tue zone
                e i dati più recenti. Puoi anticiparlo ora.
              </p>
              <p className="text-xs text-fg-subtle">
                Usa crediti Claude solo se ci sono sessioni provvisorie da confermare.
              </p>
              {refine.isError && <ErrorState message={refine.error.message} />}
              <Button loading={refine.isPending} onClick={() => refine.mutate()}>
                Aggiorna ora
              </Button>
            </>
          )}
        </div>
      </Modal>
    </>
  );
}
