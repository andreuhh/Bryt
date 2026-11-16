import { Card } from "@/components/ui/Card";
import { daysBetween, formatDay } from "@/lib/format";
import { workoutVolume } from "@/lib/plan";
import type { Workout } from "@/lib/types";

/** Planned vs executed km this week: a meter whose track is a lighter step of the fill. */
export function WeekVolumeTile({ planned, executed }: { planned: number | null; executed: number }) {
  const pct = planned ? Math.min((executed / planned) * 100, 100) : 0;
  return (
    <Card variant="card" className="flex flex-col gap-3">
      <p className="text-xs uppercase tracking-wider text-fg-subtle">Questa settimana</p>
      <p className="font-display text-4xl font-bold leading-none">
        {executed.toFixed(1).replace(".", ",")}
        <span className="ml-1 text-base font-medium text-fg-muted">/ {planned ?? "–"} km</span>
      </p>
      <div
        className="h-2 overflow-hidden rounded-pill bg-accent-pace/15"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={planned ?? 0}
        aria-valuenow={executed}
        aria-label="Chilometri della settimana"
      >
        <div className="h-full rounded-pill bg-accent-pace" style={{ width: `${pct}%` }} />
      </div>
    </Card>
  );
}

export function NextKeyTile({
  workout,
  today,
  onOpen,
}: {
  workout: Workout | undefined;
  today: string;
  onOpen: (w: Workout) => void;
}) {
  if (!workout)
    return (
      <Card variant="card" className="flex flex-col gap-2">
        <p className="text-xs uppercase tracking-wider text-fg-subtle">Prossimo appuntamento</p>
        <p className="text-sm text-fg-muted">Nessuna sessione chiave in arrivo.</p>
      </Card>
    );
  const days = daysBetween(today, workout.scheduled_date);
  return (
    <Card variant="card" className="p-0">
      <button type="button" onClick={() => onOpen(workout)} className="flex w-full flex-col gap-2 p-4 text-left">
        <p className="text-xs uppercase tracking-wider text-fg-subtle">Prossimo appuntamento</p>
        <p className="font-display text-4xl font-bold leading-none">
          {days === 0 ? "Oggi" : days}
          {days > 0 && <span className="ml-1 text-base font-medium text-fg-muted">{days === 1 ? "giorno" : "giorni"}</span>}
        </p>
        <p className="truncate text-sm text-fg">{workout.title}</p>
        <p className="text-xs text-fg-subtle first-letter:uppercase">
          {formatDay(workout.scheduled_date)}
          {workoutVolume(workout) && ` · ${workoutVolume(workout)}`}
        </p>
      </button>
    </Card>
  );
}
