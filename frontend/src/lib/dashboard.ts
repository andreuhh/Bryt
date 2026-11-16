/** Pure helpers for the dashboard (no React). */

import type { Activity, NutritionRecovery, Workout } from "@/lib/types";

const localDay = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Rome" });

/** Local calendar day (Europe/Rome) of an activity's UTC start time. */
export const activityDay = (a: Activity) => localDay.format(new Date(a.start_time));

export function activitiesByDay(activities: Activity[]): Map<string, Activity[]> {
  const map = new Map<string, Activity[]>();
  for (const a of activities) map.set(activityDay(a), [...(map.get(activityDay(a)) ?? []), a]);
  return map;
}

export function workoutsByDay(workouts: Workout[]): Map<string, Workout[]> {
  const map = new Map<string, Workout[]>();
  for (const w of workouts) map.set(w.scheduled_date, [...(map.get(w.scheduled_date) ?? []), w]);
  return map;
}

/** Sessions we can verify from recordings (strength and rest have no activity file). */
export const isRun = (w: Workout) => w.workout_type !== "REST" && w.workout_type !== "STRENGTH";

export type Readiness = NutritionRecovery["recovery_protocol"]["readiness_next_session"];

export const READINESS: Record<Readiness, { label: string; tone: "pace" | "load" }> = {
  READY: { label: "Pronto", tone: "pace" },
  CAUTION: { label: "Con cautela", tone: "load" },
  REST: { label: "Riposo consigliato", tone: "load" },
};

export const SURFACE_LABEL = {
  ASPHALT: "Asfalto",
  GRAVEL: "Sterrato",
  TRAIL: "Trail",
  TRACK: "Pista",
  TREADMILL: "Tapis roulant",
  MIXED: "Misto",
} as const;
