import Link from "next/link";

import { IconCheck } from "@/components/icons";
import { Badge } from "@/components/ui/Badge";
import { activitiesByDay, isRun, workoutsByDay } from "@/lib/dashboard";
import { addDays, formatWeekday, km, pace, parseDay } from "@/lib/format";
import { workoutDot, workoutVolume } from "@/lib/plan";
import type { Activity, Workout } from "@/lib/types";

/** Monday → Sunday: what was planned and what was actually recorded, side by side. */
export function WeekStrip({
  monday,
  today,
  workouts,
  activities,
  onOpen,
}: {
  monday: string;
  today: string;
  workouts: Workout[];
  activities: Activity[];
  onOpen: (w: Workout) => void;
}) {
  const plannedByDay = workoutsByDay(workouts);
  const doneByDay = activitiesByDay(activities);
  const days = Array.from({ length: 7 }, (_, i) => addDays(monday, i));

  return (
    <ol className="grid grid-cols-1 gap-2 md:grid-cols-7">
      {days.map((day) => {
        const planned = plannedByDay.get(day) ?? [];
        const done = doneByDay.get(day) ?? [];
        const isToday = day === today;
        const past = day < today;
        const missed = past && done.length === 0 && planned.some((w) => isRun(w) && w.status !== "COMPLETED");
        return (
          <li
            key={day}
            className={`flex flex-col gap-2 rounded-card border p-3 md:min-h-32 ${
              isToday ? "border-line-strong bg-elevated" : "border-line bg-surface"
            }`}
          >
            <p className="flex items-baseline gap-1.5 text-xs text-fg-subtle">
              <span className="capitalize">{formatWeekday(day)}</span>
              <span className={`metric text-sm ${isToday ? "font-semibold text-fg" : ""}`}>
                {parseDay(day).getDate()}
              </span>
              {isToday && <span className="text-fg-muted">· oggi</span>}
            </p>

            {planned.map((w) => (
              <button
                key={w.id}
                type="button"
                onClick={() => onOpen(w)}
                className="flex flex-col gap-0.5 rounded-lg text-left hover:opacity-80"
              >
                <span className="flex items-start gap-1.5 text-xs leading-snug">
                  <span className={`mt-1 size-1.5 shrink-0 rounded-full ${workoutDot(w.workout_type)}`} />
                  <span className={w.workout_type === "REST" ? "text-fg-subtle" : "text-fg"}>{w.title}</span>
                </span>
                {workoutVolume(w) && <span className="metric pl-3 text-[11px] text-fg-subtle">{workoutVolume(w)}</span>}
                {w.status === "MODIFIED" && (
                  <span className="pl-3">
                    <Badge className="text-[10px]">
                      Modificata
                    </Badge>
                  </span>
                )}
              </button>
            ))}

            <div className="mt-auto flex flex-col gap-1">
              {done.map((a) => (
                <Link
                  key={a.id}
                  href={`/activity/${a.id}`}
                  className="metric flex items-center gap-1 rounded-lg bg-accent-pace/10 px-2 py-1 text-[11px] text-accent-pace hover:bg-accent-pace/20"
                >
                  <IconCheck width={12} height={12} />
                  {km(a.distance_m)} km · {pace(a.avg_pace_s_per_km)}
                </Link>
              ))}
              {missed && <span className="text-[11px] text-fg-subtle">Non registrata</span>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
