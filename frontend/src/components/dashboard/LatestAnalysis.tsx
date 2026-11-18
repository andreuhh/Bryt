"use client";

import Link from "next/link";

import { IconAlert, IconCheck, IconChevron } from "@/components/icons";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/States";
import { activityDay, analysisErrorMessage } from "@/lib/dashboard";
import { formatDay, km, pace } from "@/lib/format";
import { useActivityReport, useAnalyzeInBackground } from "@/lib/queries";
import type { Activity, ActivityReport, AgentAlert } from "@/lib/types";

const SEVERITY: Record<AgentAlert["severity"], { label: string; tone: "load" | "neutral" }> = {
  CRITICAL: { label: "Critico", tone: "load" },
  WARNING: { label: "Attenzione", tone: "load" },
  INFO: { label: "Info", tone: "neutral" },
};

export function LatestAnalysis({
  activity,
  watching,
  onAnalysisStarted,
}: {
  activity: Activity | undefined;
  watching: boolean;
  onAnalysisStarted: (id: string) => void;
}) {
  const report = useActivityReport(activity?.id ?? null, watching);
  const analyze = useAnalyzeInBackground();

  if (!activity)
    return (
      <Card>
        <h2 className="font-semibold">Ultima analisi</h2>
        <p className="mt-2 text-sm text-fg-muted">Carica la tua prima corsa: gli agent la analizzeranno qui.</p>
      </Card>
    );

  const data = report.data;
  const running = report.inProgress;

  return (
    <Card className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wider text-fg-subtle">Ultima analisi</p>
          <h2 className="mt-1 font-semibold">{activity.name ?? "Corsa"}</h2>
          <p className="metric text-sm text-fg-muted first-letter:uppercase">
            {formatDay(activityDay(activity))} · {km(activity.distance_m)} km · {pace(activity.avg_pace_s_per_km)}/km
          </p>
        </div>
        <Link
          href={`/activity/${activity.id}`}
          className="flex shrink-0 items-center gap-1 rounded-pill bg-elevated px-3 py-1.5 text-xs text-fg hover:bg-elevated-hover"
        >
          Dettaglio <IconChevron width={14} height={14} />
        </Link>
      </div>

      {report.isPending ? (
        <Skeleton className="h-24" />
      ) : running ? (
        <PipelineProgress report={data} />
      ) : !data?.mechanical_load ? (
        <div className="flex flex-col items-start gap-3">
          <p className="text-sm text-fg-muted">Questa corsa non è ancora stata analizzata dagli agent.</p>
          <Button
            size="sm"
            loading={analyze.isPending}
            onClick={() => analyze.mutate(activity.id, { onSuccess: () => onAnalysisStarted(activity.id) })}
          >
            Analizza ora
          </Button>
          {analyze.isError && <p className="text-sm text-fg-muted">{analysisErrorMessage(analyze.error)}</p>}
        </div>
      ) : data.mechanical_load.status === "ERROR" || !data.mechanical_load.output ? (
        <div className="flex flex-col items-start gap-3 text-sm">
          <p className="text-fg-muted">L&apos;analisi non è riuscita: {data.mechanical_load.error}</p>
          <Button
            size="sm"
            variant="secondary"
            loading={analyze.isPending}
            onClick={() => analyze.mutate(activity.id, { onSuccess: () => onAnalysisStarted(activity.id) })}
          >
            Riprova
          </Button>
          {analyze.isError && <p className="text-fg-muted">{analysisErrorMessage(analyze.error)}</p>}
        </div>
      ) : (
        <AnalysisSummary report={data} />
      )}
    </Card>
  );
}

function PipelineProgress({ report }: { report: ActivityReport | undefined }) {
  const steps = [
    { label: "Analisi meccanica", done: Boolean(report?.mechanical_load) },
    { label: "Adattamento del piano", done: Boolean(report?.plan_adjustment || report?.nutrition_recovery) },
    { label: "Nutrizione e recupero", done: Boolean(report?.nutrition_recovery) },
  ];
  const current = steps.findIndex((s) => !s.done);
  return (
    <ol className="flex flex-col gap-2 text-sm" aria-live="polite">
      {steps.map((s, i) => (
        <li key={s.label} className={`flex items-center gap-2 ${s.done ? "text-fg" : i === current ? "text-fg" : "text-fg-subtle"}`}>
          {s.done ? (
            <IconCheck width={16} height={16} className="text-accent-pace" />
          ) : i === current ? (
            <span className="size-4 animate-spin rounded-full border-2 border-fg-muted border-t-transparent" />
          ) : (
            <span className="size-4 rounded-full border border-line-strong" />
          )}
          {s.label}
        </li>
      ))}
      <li className="text-xs text-fg-subtle">Di solito serve un paio di minuti.</li>
    </ol>
  );
}

function AnalysisSummary({ report }: { report: ActivityReport }) {
  const ml = report.mechanical_load!.output!;
  const alerts = ml.alerts ?? [];
  const adjusted = report.plan_adjustment?.output?.adjustments.filter((a) => a.action !== "KEEP").length ?? 0;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm leading-relaxed text-fg">{ml.summary}</p>
      {alerts.length > 0 && (
        <ul className="flex flex-col gap-2">
          {alerts.map((a) => (
            <li
              key={a.code + a.title}
              className={`flex gap-3 rounded-card p-3 text-sm ${a.severity === "INFO" ? "bg-elevated" : "bg-accent-load/10"}`}
            >
              <IconAlert
                width={18}
                height={18}
                className={`mt-0.5 shrink-0 ${a.severity === "INFO" ? "text-fg-muted" : "text-accent-load"}`}
              />
              <div className="flex flex-col gap-1">
                <p className="flex flex-wrap items-center gap-2 font-medium text-fg">
                  {a.title} <Badge tone={SEVERITY[a.severity].tone}>{SEVERITY[a.severity].label}</Badge>
                </p>
                <p className="text-fg-muted">{a.message}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
      {adjusted > 0 && (
        <Link href="/plan" className="text-sm text-fg underline decoration-line-strong underline-offset-4">
          Il coach ha adattato {adjusted} {adjusted === 1 ? "sessione" : "sessioni"} dei prossimi giorni
        </Link>
      )}
    </div>
  );
}
