"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { MechanicalCard, NutritionCard, RecoveryCard } from "@/components/activity/AgentCards";
import { DivergenceCard } from "@/components/activity/DivergenceCard";
import { TelemetryCharts } from "@/components/charts/TelemetryCharts";
import { ContextTagsModal } from "@/components/dashboard/ContextTagsModal";
import { IconChevron } from "@/components/icons";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { buildSeries, divergenceSegments } from "@/lib/activity";
import { activityDay, SURFACE_LABEL } from "@/lib/dashboard";
import { duration, formatLong, km, pace } from "@/lib/format";
import {
  reportComplete,
  useActivity,
  useActivityReport,
  useActivityStreams,
  useAnalyzeInBackground,
} from "@/lib/queries";
import type { Activity } from "@/lib/types";

export function ActivityView() {
  const { id } = useParams<{ id: string }>();
  const activity = useActivity(id);
  const streams = useActivityStreams(id);
  const [watching, setWatching] = useState(false);
  const report = useActivityReport(id, watching);
  const analyze = useAnalyzeInBackground();
  const [editing, setEditing] = useState<Activity | null>(null);

  const rows = useMemo(() => (streams.data ? buildSeries(streams.data) : []), [streams.data]);
  const divergence = activity.data?.computed_metrics.cadence_hr_divergence;
  const segments = useMemo(() => divergenceSegments(rows, divergence), [rows, divergence]);

  if (activity.isPending) return <Skeleton className="h-96" />;
  if (activity.isError) return <ErrorState message={activity.error.message} onRetry={() => activity.refetch()} />;

  const a = activity.data;
  const data = report.data;
  const running = watching && !reportComplete(data);
  const startAnalysis = () => analyze.mutate(id, { onSuccess: () => setWatching(true) });

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-3">
        <Link href="/dashboard" className="flex w-fit items-center gap-1 text-sm text-fg-muted hover:text-fg">
          <IconChevron width={16} height={16} className="rotate-180" /> Dashboard
        </Link>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold sm:text-4xl">{a.name ?? "Corsa"}</h1>
            <p className="mt-1 text-sm text-fg-muted first-letter:uppercase">
              {formatLong(activityDay(a))} ·{" "}
              {new Date(a.start_time).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Rome" })}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {a.surface && <Badge>{SURFACE_LABEL[a.surface]}</Badge>}
            <Badge tone="outline">{a.source === "INTERVALS" ? "Intervals.icu" : "Caricata a mano"}</Badge>
            <Button variant="secondary" size="sm" onClick={() => setEditing(a)}>
              Modifica tag
            </Button>
          </div>
        </div>
      </header>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {[
          { label: "Distanza", value: km(a.distance_m), unit: "km" },
          { label: "Tempo", value: duration(a.moving_time_s ?? a.duration_s), unit: "" },
          { label: "Passo medio", value: pace(a.avg_pace_s_per_km), unit: "/km" },
          { label: "FC media", value: a.avg_hr ? String(Math.round(a.avg_hr)) : "–", unit: a.max_hr ? `max ${Math.round(a.max_hr)}` : "" },
          { label: "Cadenza", value: a.avg_cadence_spm ? String(Math.round(a.avg_cadence_spm)) : "–", unit: "spm" },
          { label: "Dislivello", value: a.elevation_gain_m !== null ? `+${Math.round(a.elevation_gain_m)}` : "–", unit: "m" },
        ].map((m) => (
          <Card key={m.label} variant="card" className="flex flex-col gap-1">
            <span className="text-xs uppercase tracking-wider text-fg-subtle">{m.label}</span>
            <span className="font-display text-2xl font-bold">
              {m.value}
              {m.unit && <span className="ml-1 text-sm font-medium text-fg-muted">{m.unit}</span>}
            </span>
          </Card>
        ))}
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <Card className="min-w-0 lg:col-span-3">
          <h2 className="font-semibold">Telemetria</h2>
          <p className="mb-4 text-sm text-fg-muted">
            Passo, frequenza cardiaca e cadenza lungo la corsa. Il cedimento si misura confrontando il tratto
            finale con il tratto di riferimento, la parte regolare della corsa.
          </p>
          {streams.isPending ? (
            <Skeleton className="h-96" />
          ) : streams.isError ? (
            <ErrorState message={streams.error.message} />
          ) : (
            <TelemetryCharts rows={rows} segments={segments} />
          )}
        </Card>
        <div className="min-w-0 lg:col-span-2">{divergence && <DivergenceCard divergence={divergence} />}</div>
      </div>

      <section className="flex flex-col gap-4">
        <h2 className="text-xl font-semibold">Analisi degli agent</h2>
        {report.isPending ? (
          <Skeleton className="h-48" />
        ) : running ? (
          <Card className="text-sm text-fg-muted">Gli agent stanno analizzando la corsa: la pagina si aggiorna da sola.</Card>
        ) : !data?.mechanical_load?.output ? (
          <Card className="flex flex-col items-start gap-3">
            <p className="text-sm text-fg-muted">
              {data?.mechanical_load?.status === "ERROR"
                ? `L'analisi non è riuscita: ${data.mechanical_load.error}`
                : "Questa corsa non è ancora stata analizzata."}
            </p>
            <Button size="sm" loading={analyze.isPending} onClick={startAnalysis}>
              Analizza ora
            </Button>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="lg:col-span-2">
              <MechanicalCard activityId={id} run={data.mechanical_load} adjustment={data.plan_adjustment ?? null} />
            </div>
            {data.nutrition_recovery?.output ? (
              <>
                <NutritionCard activityId={id} run={data.nutrition_recovery} />
                <RecoveryCard activityId={id} run={data.nutrition_recovery} />
              </>
            ) : (
              <Card className="text-sm text-fg-muted lg:col-span-2">
                Nutrizione e recupero non disponibili{data.nutrition_recovery?.error ? `: ${data.nutrition_recovery.error}` : "."}
              </Card>
            )}
          </div>
        )}
      </section>

      <ContextTagsModal
        title="Modifica il contesto"
        activity={editing}
        onClose={() => setEditing(null)}
        onAnalysisStarted={() => setWatching(true)}
      />
    </div>
  );
}
