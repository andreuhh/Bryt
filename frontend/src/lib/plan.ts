/** Pure helpers for the plan views (no React). */

import { addDays, km, mondayOf, duration, pace } from "@/lib/format";
import type { Activity, PlanBlock, PlanWeek, TrainingPlan, Workout, WorkoutStep, WorkoutType } from "@/lib/types";

export const WORKOUT_LABEL: Record<WorkoutType, string> = {
  EASY: "Facile",
  RECOVERY: "Rigenerante",
  LONG: "Lungo",
  THRESHOLD: "Soglia",
  INTERVALS: "Ripetute",
  TEMPO: "Medio",
  HILLS: "Salite",
  RACE_PACE: "Passo gara",
  RACE: "Gara",
  STRENGTH: "Forza",
  REST: "Riposo",
};

const AEROBIC: WorkoutType[] = ["EASY", "RECOVERY", "LONG", "RACE"];
const QUALITY: WorkoutType[] = ["THRESHOLD", "INTERVALS", "TEMPO", "RACE_PACE", "HILLS"];

/** Dot color class: aerobic = pace accent, quality = strong neutral, the rest muted. */
export function workoutDot(type: WorkoutType): string {
  if (AEROBIC.includes(type)) return "bg-accent-pace";
  if (QUALITY.includes(type)) return "bg-fg";
  if (type === "STRENGTH") return "bg-fg-muted";
  return "bg-line-strong";
}

export const PHASE_LABEL: Record<PlanBlock["phase"], string> = {
  BASE: "Base",
  BUILD: "Costruzione",
  SPECIFIC: "Specifico",
  PEAK: "Picco",
  TAPER: "Scarico",
  TRANSITION: "Transizione",
};

export const LOAD_LABEL: Record<PlanWeek["load_type"], string> = {
  LOAD: "Carico",
  DELOAD: "Scarico",
  RACE: "Gara",
};

export function workoutVolume(w: {
  target_distance_m?: number | null;
  target_duration_s?: number | null;
}): string | null {
  if (w.target_distance_m) return `${km(w.target_distance_m)} km`;
  if (w.target_duration_s) return duration(w.target_duration_s);
  return null;
}

const STEP_LABEL: Record<WorkoutStep["kind"], string> = {
  WARMUP: "Riscaldamento",
  WORK: "Lavoro",
  RECOVERY: "Recupero",
  COOLDOWN: "Defaticamento",
};

export function stepLabel(step: WorkoutStep): { title: string; target: string | null } {
  const length = step.distance_m
    ? step.distance_m >= 1000
      ? `${km(step.distance_m)} km`
      : `${step.distance_m} m`
    : step.duration_s
      ? step.duration_s < 60
        ? `${step.duration_s}"`
        : duration(step.duration_s)
      : "";
  const reps = step.repeat && step.repeat > 1 ? `${step.repeat} × ` : "";
  const target = [
    step.target_zone,
    step.target_pace ? `${pace(step.target_pace.fast_s_per_km)}–${pace(step.target_pace.slow_s_per_km)}/km` : null,
    step.target_hr ? `${step.target_hr.min_bpm}–${step.target_hr.max_bpm} bpm` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return { title: `${STEP_LABEL[step.kind]} ${reps}${length}`.trim(), target: target || null };
}

export type PlanWeekView = PlanWeek & {
  block: PlanBlock;
  end_date: string;
  workouts: Workout[];
  executed_km: number;
};

export function planWeeks(plan: TrainingPlan, workouts: Workout[], activities: Activity[]): PlanWeekView[] {
  const executed = executedKmByWeek(activities);
  const byWeek = new Map<string, Workout[]>();
  for (const w of workouts) {
    const key = mondayOf(w.scheduled_date);
    byWeek.set(key, [...(byWeek.get(key) ?? []), w]);
  }
  return plan.blocks
    .flatMap((block) => block.weeks.map((week) => ({ week, block })))
    .sort((a, b) => a.week.start_date.localeCompare(b.week.start_date))
    .map(({ week, block }) => {
      const key = mondayOf(week.start_date);
      return {
        ...week,
        block,
        end_date: addDays(key, 6),
        workouts: (byWeek.get(key) ?? []).sort(
          (a, b) => a.scheduled_date.localeCompare(b.scheduled_date) || a.session_slot.localeCompare(b.session_slot),
        ),
        executed_km: executed.get(key) ?? 0,
      };
    });
}

const localDay = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Rome" });

export function executedKmByWeek(activities: Activity[]): Map<string, number> {
  const totals = new Map<string, number>();
  for (const a of activities) {
    const key = mondayOf(localDay.format(new Date(a.start_time)));
    totals.set(key, (totals.get(key) ?? 0) + a.distance_m / 1000);
  }
  return totals;
}
