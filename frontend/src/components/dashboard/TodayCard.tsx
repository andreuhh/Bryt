import Link from "next/link";

import { WorkoutBadges } from "@/components/plan/WorkoutBadges";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { READINESS, type Readiness } from "@/lib/dashboard";
import { formatDay, km, pace } from "@/lib/format";
import { stepLabel, WORKOUT_LABEL, workoutDot, workoutVolume } from "@/lib/plan";
import type { Activity, Workout } from "@/lib/types";

export function TodayCard({
  today,
  workouts,
  activities,
  next,
  readiness,
  onOpen,
}: {
  today: string;
  workouts: Workout[];
  activities: Activity[];
  next: Workout | undefined;
  readiness: Readiness | null;
  onOpen: (w: Workout) => void;
}) {
  const sessions = workouts.filter((w) => w.workout_type !== "REST");

  return (
    <Card className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs uppercase tracking-wider text-fg-subtle first-letter:uppercase">
          Oggi · {formatDay(today)}
        </p>
        {readiness && (
          <Badge tone={READINESS[readiness].tone} title="Dall'ultima analisi di recupero">
            {READINESS[readiness].label}
          </Badge>
        )}
      </div>

      {sessions.length === 0 ? (
        <div className="flex flex-col gap-2">
          <h2 className="text-3xl font-bold">Riposo</h2>
          <p className="text-sm text-fg-muted">
            Nessuna corsa in programma. Il recupero fa parte dell&apos;allenamento.
          </p>
          {next && (
            <button type="button" onClick={() => onOpen(next)} className="mt-2 self-start text-left text-sm">
              <span className="text-fg-subtle">Prossima sessione · </span>
              <span className="text-fg underline decoration-line-strong underline-offset-4">{next.title}</span>
              <span className="text-fg-subtle first-letter:uppercase"> · {formatDay(next.scheduled_date)}</span>
            </button>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {sessions.map((w) => {
            const work = w.structure.find((s) => s.kind === "WORK");
            const done = activities.find((a) => a.id === w.activity_id);
            return (
              <button
                key={w.id}
                type="button"
                onClick={() => onOpen(w)}
                className="flex flex-col gap-2 rounded-card text-left transition hover:opacity-90"
              >
                <span className="flex items-center gap-2 text-sm text-fg-muted">
                  <span className={`size-2 rounded-full ${workoutDot(w.workout_type)}`} />
                  {WORKOUT_LABEL[w.workout_type]}
                  {w.session_slot !== "SINGLE" && <span>· {w.session_slot}</span>}
                </span>
                <span className="text-2xl font-bold leading-tight sm:text-3xl">{w.title}</span>
                <span className="flex flex-wrap items-center gap-3">
                  {workoutVolume(w) && <span className="metric text-lg text-fg">{workoutVolume(w)}</span>}
                  {work && <span className="metric text-sm text-fg-muted">{stepLabel(work).target}</span>}
                </span>
                <WorkoutBadges workout={w} />
                {done && (
                  <span className="metric text-sm text-accent-pace">
                    Fatto · {km(done.distance_m)} km a {pace(done.avg_pace_s_per_km)}/km
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {sessions.length === 0 && workouts.length === 0 && !next && (
        <Link href="/plan" className="text-sm text-fg-muted underline underline-offset-4">
          Apri il piano
        </Link>
      )}
    </Card>
  );
}
