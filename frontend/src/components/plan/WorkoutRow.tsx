import { IconChevron } from "@/components/icons";
import { WorkoutBadges } from "@/components/plan/WorkoutBadges";
import { formatWeekday, parseDay } from "@/lib/format";
import { workoutDot, workoutVolume } from "@/lib/plan";
import type { Workout } from "@/lib/types";

export function WorkoutRow({
  workout,
  today,
  onOpen,
}: {
  workout: Workout;
  today: string;
  onOpen: (w: Workout) => void;
}) {
  const isToday = workout.scheduled_date === today;
  const rest = workout.workout_type === "REST";
  const volume = workoutVolume(workout);

  return (
    <button
      type="button"
      onClick={() => onOpen(workout)}
      className={`group flex w-full items-center gap-3 rounded-card px-3 py-2.5 text-left transition hover:bg-elevated ${
        isToday ? "bg-elevated" : ""
      }`}
    >
      <span className="w-12 shrink-0 text-xs capitalize text-fg-subtle">
        <span className="block">{formatWeekday(workout.scheduled_date)}</span>
        <span className={`metric text-sm ${isToday ? "font-semibold text-fg" : "text-fg-muted"}`}>
          {parseDay(workout.scheduled_date).getDate()}
        </span>
      </span>
      <span className={`size-2 shrink-0 rounded-full ${workoutDot(workout.workout_type)}`} aria-hidden />
      <span className="flex min-w-0 flex-1 flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
        <span className={`truncate text-sm ${rest ? "text-fg-subtle" : "text-fg"}`}>{workout.title}</span>
        <WorkoutBadges workout={workout} compact />
      </span>
      {volume && <span className="metric shrink-0 text-sm text-fg-muted">{volume}</span>}
      <IconChevron className="shrink-0 text-fg-subtle opacity-0 transition group-hover:opacity-100" width={16} />
    </button>
  );
}
