import Link from "next/link";
import type { ReactNode } from "react";

import { FeedbackButtons } from "@/components/activity/FeedbackButtons";
import { IconAlert } from "@/components/icons";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { READINESS } from "@/lib/dashboard";
import type { ActivityReport } from "@/lib/types";

type Runs = Required<ActivityReport>;

const LOAD_LEVEL = { LOW: "Basso", MODERATE: "Moderato", HIGH: "Alto", VERY_HIGH: "Molto alto" } as const;
const FACTOR = {
  CAFFEINE: "Caffeina",
  JET_LAG: "Jet lag",
  TRAVEL: "Viaggio",
  SLEEP: "Sonno",
  STRESS: "Stress",
  HEAT: "Caldo",
  ILLNESS: "Malessere",
  OTHER: "Altro",
} as const;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-xs font-medium uppercase tracking-wider text-fg-subtle">{title}</h3>
      {children}
    </section>
  );
}

export function MechanicalCard({ activityId, run, adjustment }: { activityId: string; run: NonNullable<Runs["mechanical_load"]>; adjustment: Runs["plan_adjustment"] }) {
  const out = run.output!;
  const load = out.mechanical_load;
  const changed = adjustment?.output?.adjustments.filter((a) => a.action !== "KEEP") ?? [];
  return (
    <Card className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-fg-subtle">Carico meccanico</p>
          <p className="font-display text-4xl font-bold">
            {load.load_score}
            <span className="ml-1 text-base font-medium text-fg-muted">/100</span>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {run.depth === "LIGHT" && (
            <Badge tone="outline" title="Corsa facile senza segnali d'allarme: analisi sintetica">
              Analisi rapida
            </Badge>
          )}
          <Badge tone={load.load_level === "HIGH" || load.load_level === "VERY_HIGH" ? "load" : "neutral"}>
            Carico {LOAD_LEVEL[load.load_level].toLowerCase()}
          </Badge>
          <Badge tone={load.eccentric_stress === "HIGH" || load.eccentric_stress === "VERY_HIGH" ? "load" : "neutral"}>
            Eccentrico {LOAD_LEVEL[load.eccentric_stress].toLowerCase()}
          </Badge>
        </div>
      </div>

      <p className="text-sm leading-relaxed">{out.summary}</p>
      {run.depth === "LIGHT" && (
        <p className="text-xs text-fg-subtle">
          Corsa facile senza segnali d&apos;allarme: analisi sintetica. Se aggiorni i tag, la nuova analisi è completa.
        </p>
      )}

      {(out.alerts ?? []).length > 0 && (
        <ul className="flex flex-col gap-2">
          {out.alerts!.map((a) => (
            <li key={a.code + a.title} className={`flex gap-3 rounded-card p-3 text-sm ${a.severity === "INFO" ? "bg-elevated" : "bg-accent-load/10"}`}>
              <IconAlert width={18} height={18} className={`mt-0.5 shrink-0 ${a.severity === "INFO" ? "text-fg-muted" : "text-accent-load"}`} />
              <div>
                <p className="font-medium">{a.title}</p>
                <p className="text-fg-muted">{a.message}</p>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Section title="Carico rispetto alla tua storia">
        <p className="text-sm text-fg-muted">{load.explanation}</p>
      </Section>

      {(out.contextual_factors ?? []).length > 0 && (
        <Section title="Fattori di contesto">
          <ul className="flex flex-col gap-2 text-sm">
            {out.contextual_factors!.map((c, i) => (
              <li key={i} className="flex gap-2">
                <Badge className="h-fit">{FACTOR[c.factor]}</Badge>
                <span className="text-fg-muted">{c.explanation}</span>
              </li>
            ))}
          </ul>
          {out.false_alarm_suppressed && (
            <p className="text-xs text-accent-pace">Il contesto spiega l&apos;anomalia: nessun calo di forma.</p>
          )}
        </Section>
      )}

      <Section title="Rispetto al piano">
        <p className="text-sm text-fg-muted">
          <span className="metric text-fg">{out.execution.compliance_score}/100</span> · {out.execution.notes}
        </p>
      </Section>

      {changed.length > 0 && (
        <Section title="Piano adattato">
          <ul className="flex flex-col gap-1 text-sm">
            {changed.map((a) => (
              <li key={a.workout_id} className="text-fg-muted">
                <span className="text-fg">{a.new_workout?.title ?? "Riposo"}</span> · {a.reason}
              </li>
            ))}
          </ul>
          <Link href="/plan" className="text-sm underline decoration-line-strong underline-offset-4">
            Vedi nel piano
          </Link>
        </Section>
      )}

      <FeedbackButtons activityId={activityId} runId={run.id} current={run.feedback} />
    </Card>
  );
}

export function NutritionCard({ activityId, run }: { activityId: string; run: NonNullable<Runs["nutrition_recovery"]> }) {
  const n = run.output!.nutrition_protocol;
  return (
    <Card className="flex flex-col gap-5 border-accent-nutrition/30">
      <div>
        <p className="text-xs uppercase tracking-wider text-accent-nutrition">Nutrizione</p>
        <div className="mt-2 grid grid-cols-2 gap-4">
          <div>
            <p className="font-display text-3xl font-bold">
              {n.daily_carbs_g_per_kg}
              <span className="ml-1 text-sm font-medium text-fg-muted">g/kg</span>
            </p>
            <p className="text-xs text-fg-subtle">carboidrati al giorno</p>
          </div>
          <div>
            <p className="font-display text-3xl font-bold">
              {n.daily_protein_g_per_kg}
              <span className="ml-1 text-sm font-medium text-fg-muted">g/kg</span>
            </p>
            <p className="text-xs text-fg-subtle">proteine al giorno</p>
          </div>
        </div>
      </div>
      <Section title="Dopo la corsa">
        <p className="metric text-sm text-fg-muted">
          Entro {n.post_session.window_minutes}′: {n.post_session.carbs_g} g di carboidrati + {n.post_session.protein_g} g di proteine
        </p>
      </Section>
      <Section title="Idratazione">
        <p className="metric text-sm text-fg-muted">
          {n.electrolytes.fluids_ml} ml · {n.electrolytes.sodium_mg} mg di sodio
          {n.electrolytes.notes && ` · ${n.electrolytes.notes}`}
        </p>
      </Section>
      <Section title="Caffeina">
        <p className="text-sm text-fg-muted">
          {n.caffeine.recommended
            ? [
                n.caffeine.dose_mg_per_kg && `${n.caffeine.dose_mg_per_kg} mg/kg`,
                n.caffeine.minutes_before_session && `${n.caffeine.minutes_before_session}′ prima`,
                n.caffeine.cutoff_local_time && `non dopo le ${n.caffeine.cutoff_local_time}`,
              ]
                .filter(Boolean)
                .join(" · ")
            : "Meglio evitarla"}
          {n.caffeine.notes && <span className="mt-1 block">{n.caffeine.notes}</span>}
        </p>
      </Section>
      {n.next_session_fueling && (
        <Section title="Prossima sessione">
          <p className="text-sm text-fg-muted">{n.next_session_fueling}</p>
        </Section>
      )}
      {(n.notes ?? []).length > 0 && (
        <ul className="flex list-disc flex-col gap-1 pl-5 text-sm text-fg-muted marker:text-accent-nutrition">
          {n.notes!.map((note, i) => (
            <li key={i}>{note}</li>
          ))}
        </ul>
      )}
      <FeedbackButtons activityId={activityId} runId={run.id} current={run.feedback} />
    </Card>
  );
}

export function RecoveryCard({ activityId, run }: { activityId: string; run: NonNullable<Runs["nutrition_recovery"]> }) {
  const r = run.output!.recovery_protocol;
  const readiness = READINESS[r.readiness_next_session];
  return (
    <Card className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-fg-subtle">Recupero</p>
          <p className="font-display text-3xl font-bold">
            {r.sleep.target_hours}
            <span className="ml-1 text-sm font-medium text-fg-muted">h di sonno</span>
          </p>
          {r.sleep.bedtime_local && <p className="text-xs text-fg-subtle">a letto entro le {r.sleep.bedtime_local}</p>}
        </div>
        <Badge tone={readiness.tone}>Prossima sessione: {readiness.label.toLowerCase()}</Badge>
      </div>
      {r.sleep.notes && <p className="text-sm text-fg-muted">{r.sleep.notes}</p>}
      {(r.mobility ?? []).length > 0 && (
        <Section title="Mobilità">
          <ul className="flex flex-col gap-2">
            {r.mobility!.map((m, i) => (
              <li key={i} className="flex items-center justify-between gap-3 rounded-card bg-elevated px-3 py-2 text-sm">
                <span>
                  {m.name}
                  <span className="block text-xs text-fg-subtle">{m.focus}</span>
                </span>
                <span className="metric shrink-0 text-fg-muted">{m.duration_min}′</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
      {r.jet_lag && (
        <Section title="Jet lag">
          <p className="text-sm text-fg-muted">{r.jet_lag.strategy}</p>
        </Section>
      )}
      {[...(r.stress_management ?? []), ...(r.notes ?? [])].length > 0 && (
        <ul className="flex list-disc flex-col gap-1 pl-5 text-sm text-fg-muted">
          {[...(r.stress_management ?? []), ...(r.notes ?? [])].map((note, i) => (
            <li key={i}>{note}</li>
          ))}
        </ul>
      )}
      <FeedbackButtons activityId={activityId} runId={run.id} current={run.feedback} />
    </Card>
  );
}
