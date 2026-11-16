"use client";

import { WorkoutBadges } from "@/components/plan/WorkoutBadges";
import { Modal } from "@/components/ui/Modal";
import { Skeleton } from "@/components/ui/States";
import { formatDay, formatLong } from "@/lib/format";
import { stepLabel, WORKOUT_LABEL, workoutVolume } from "@/lib/plan";
import { useWorkoutHistory } from "@/lib/queries";
import type { Workout, WorkoutRevision } from "@/lib/types";

const SOURCE_LABEL: Record<WorkoutRevision["source"], string> = {
  WEEKLY_REFINEMENT: "Aggiornamento settimanale",
  POST_ACTIVITY: "Dopo un'attività",
  COACH_CHAT: "Chat con il coach",
};

const REVISION_LABEL: Record<WorkoutRevision["status"], string> = {
  APPLIED: "Applicata",
  PENDING: "In attesa",
  REJECTED: "Rifiutata",
  SUPERSEDED: "Sostituita",
};

export function WorkoutModal({ workout, onClose }: { workout: Workout | null; onClose: () => void }) {
  return (
    <Modal open={workout !== null} onClose={onClose} title={workout?.title ?? ""}>
      {workout && <WorkoutDetail workout={workout} />}
    </Modal>
  );
}

function WorkoutDetail({ workout }: { workout: Workout }) {
  const history = useWorkoutHistory(workout.id);
  const volume = workoutVolume(workout);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <p className="text-sm text-fg-muted first-letter:uppercase">
          {formatDay(workout.scheduled_date)} · {WORKOUT_LABEL[workout.workout_type]}
          {volume && <span className="metric"> · {volume}</span>}
        </p>
        <WorkoutBadges workout={workout} />
      </div>

      {workout.description && <p className="text-sm leading-relaxed text-fg">{workout.description}</p>}

      {workout.structure.length > 0 && (
        <section className="flex flex-col gap-2">
          <h3 className="text-xs font-medium uppercase tracking-wider text-fg-subtle">Struttura</h3>
          <ol className="flex flex-col gap-2">
            {workout.structure.map((step, i) => {
              const { title, target } = stepLabel(step);
              return (
                <li key={i} className="rounded-card bg-elevated px-4 py-3">
                  <p className="metric text-sm font-medium">{title}</p>
                  {target && <p className="metric text-xs text-fg-muted">{target}</p>}
                  {step.notes && <p className="mt-1 text-xs text-fg-muted">{step.notes}</p>}
                </li>
              );
            })}
          </ol>
          {workout.detail_level === "PROVISIONAL" && (
            <p className="text-xs text-fg-subtle">
              Sessione provvisoria: passi e frequenze cardiache vengono calibrati con l&apos;aggiornamento
              settimanale, due settimane prima.
            </p>
          )}
        </section>
      )}

      {workout.status === "MODIFIED" && workout.modification_reason && (
        <section className="rounded-card border border-accent-load/30 bg-accent-load/10 p-4 text-sm">
          <p className="font-medium text-fg">Perché è cambiata</p>
          <p className="mt-1 text-fg-muted">{workout.modification_reason}</p>
          {workout.original_snapshot && (
            <p className="mt-2 text-xs text-fg-subtle">
              Versione originale: {workout.original_snapshot.title}
              {workoutVolume(workout.original_snapshot) && ` · ${workoutVolume(workout.original_snapshot)}`}
            </p>
          )}
        </section>
      )}

      <section className="flex flex-col gap-2">
        <h3 className="text-xs font-medium uppercase tracking-wider text-fg-subtle">Cronologia</h3>
        {history.isPending ? (
          <Skeleton className="h-14" />
        ) : history.data?.length ? (
          <ol className="flex flex-col gap-3 border-l border-line pl-4">
            {history.data.map((rev) => (
              <li key={rev.id} className="text-sm">
                <p className="text-xs text-fg-subtle">
                  {rev.created_at && formatLong(rev.created_at.slice(0, 10))} · {SOURCE_LABEL[rev.source]} ·{" "}
                  {REVISION_LABEL[rev.status]}
                </p>
                <p className="text-fg-muted">
                  {rev.before?.title ?? "–"} → <span className="text-fg">{rev.after.title}</span>
                </p>
                <p className="text-xs text-fg-subtle">{rev.reason}</p>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-fg-subtle">Nessuna modifica: è la versione originale del piano.</p>
        )}
      </section>
    </div>
  );
}
