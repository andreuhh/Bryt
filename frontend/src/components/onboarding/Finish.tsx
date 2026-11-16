"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { pace, paceRange } from "@/lib/format";
import { useCalibration, useGeneratePlan, usePlanGeneration } from "@/lib/queries";

const CONFIDENCE = {
  HIGH: { label: "Affidabilità alta", tone: "pace", text: "Basate su un risultato degli ultimi 6 mesi." },
  MEDIUM: { label: "Affidabilità media", tone: "neutral", text: "Basate su un risultato di 6-12 mesi fa." },
  LOW: {
    label: "Affidabilità bassa",
    tone: "load",
    text: "Basate su dati vecchi o indiretti: il piano inserirà presto un test per ricalibrarle.",
  },
} as const;

/** After saving the profile: zones derived from the athlete's results, then plan generation. */
export function ReviewZones({ hasActivePlan, onBack }: { hasActivePlan: boolean; onBack: () => void }) {
  const calibration = useCalibration();
  const generate = useGeneratePlan();
  const [planId, setPlanId] = useState<string | null>(null);

  if (planId) return <Generating planId={planId} onRetry={() => setPlanId(null)} />;
  if (calibration.isPending) return <Skeleton className="h-80" />;
  if (calibration.isError) return <ErrorState message={calibration.error.message} onRetry={() => calibration.refetch()} />;

  const c = calibration.data;
  const conf = CONFIDENCE[c.confidence];
  return (
    <div className="flex flex-col gap-6">
      <Card className="flex flex-col gap-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wider text-fg-subtle">Passo di soglia stimato</p>
            <p className="font-display text-5xl font-bold">
              {pace(c.threshold_pace_s_per_km)}
              <span className="ml-1 text-lg font-medium text-fg-muted">/km</span>
            </p>
          </div>
          <Badge tone={conf.tone}>{conf.label}</Badge>
        </div>
        <p className="text-sm text-fg-muted">
          {conf.text} {c.threshold_hr ? `FC di soglia: ${c.threshold_hr} bpm.` : "Zone FC non disponibili: si allena a passo e sensazioni."}
        </p>
        <table className="metric w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-fg-subtle">
              <th className="pb-2 font-normal">Zona</th>
              <th className="pb-2 text-right font-normal">Passo</th>
              <th className="pb-2 text-right font-normal">FC</th>
            </tr>
          </thead>
          <tbody>
            {c.zones.map((z) => (
              <tr key={z.code} className="border-t border-line">
                <td className="py-2">
                  <span className="text-fg">{z.code}</span> <span className="text-fg-muted">{z.label}</span>
                </td>
                <td className="py-2 text-right">{paceRange(z.pace) ?? "–"}</td>
                <td className="py-2 text-right text-fg-muted">{z.hr ? `${z.hr.min_bpm}–${z.hr.max_bpm}` : "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-xs text-fg-subtle">{c.source_notes}</p>
      </Card>

      <Card className="flex flex-col gap-4">
        <div>
          <h2 className="font-semibold">Genera il piano</h2>
          <p className="text-sm text-fg-muted">
            Il coach costruisce la periodizzazione fino alla gara e scrive ogni giorno di allenamento. Servono alcuni
            minuti.
            {hasActivePlan && " Il nuovo piano sostituirà quello attuale, che resta archiviato."}
          </p>
        </div>
        {generate.isError && <ErrorState message={generate.error.message} />}
        <div className="flex flex-wrap gap-2">
          <Button loading={generate.isPending} onClick={() => generate.mutate(undefined, { onSuccess: (plan) => setPlanId(plan.id) })}>
            Genera il mio piano
          </Button>
          <Button variant="ghost" onClick={onBack}>
            Modifica le risposte
          </Button>
          {hasActivePlan && (
            <Link href="/dashboard" className="inline-flex h-11 items-center px-3 text-sm text-fg-muted hover:text-fg">
              Salva solo il profilo
            </Link>
          )}
        </div>
      </Card>
    </div>
  );
}

const PHASES = [
  "Leggo profilo, risultati e storico…",
  "Costruisco la periodizzazione fino alla gara…",
  "Scrivo gli allenamenti, un blocco alla volta…",
  "Controllo giorni disponibili, zone e progressione…",
];

function Generating({ planId, onRetry }: { planId: string; onRetry: () => void }) {
  const router = useRouter();
  const plan = usePlanGeneration(planId);
  const [seconds, setSeconds] = useState(0);
  const status = plan.data?.status;

  useEffect(() => {
    if (status !== "GENERATING" && status !== undefined) return;
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [status]);

  useEffect(() => {
    if (status === "ACTIVE") {
      const t = setTimeout(() => router.push("/plan"), 1500);
      return () => clearTimeout(t);
    }
  }, [status, router]);

  if (status === "FAILED")
    return (
      <Card className="flex flex-col items-start gap-4">
        <h2 className="font-semibold">La generazione non è riuscita</h2>
        <p className="text-sm text-fg-muted">{plan.data?.generation_error}</p>
        <Button onClick={onRetry}>Riprova</Button>
      </Card>
    );

  if (status === "ACTIVE")
    return (
      <Card className="flex flex-col items-start gap-3">
        <h2 className="text-2xl font-bold">Il tuo piano è pronto</h2>
        <p className="text-sm text-fg-muted">{plan.data?.name}</p>
        <Link href="/plan" className="rounded-pill bg-fg px-5 py-2.5 text-sm font-medium text-canvas">
          Apri il piano
        </Link>
      </Card>
    );

  const phase = PHASES[Math.min(Math.floor(seconds / 45), PHASES.length - 1)];
  return (
    <Card className="flex flex-col items-center gap-5 py-12 text-center">
      <span className="size-10 animate-spin rounded-full border-2 border-fg-muted border-t-transparent" />
      <div aria-live="polite">
        <p className="font-semibold">{phase}</p>
        <p className="metric mt-1 text-sm text-fg-subtle">
          {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")} · di solito 5-10 minuti
        </p>
      </div>
      <p className="max-w-sm text-xs text-fg-subtle">Puoi chiudere questa pagina: il piano continua a generarsi e lo troverai in Piano.</p>
    </Card>
  );
}
