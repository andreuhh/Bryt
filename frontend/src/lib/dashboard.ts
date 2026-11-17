/** Pure helpers for the dashboard (no React). */

import { ApiError } from "@/lib/api";
import type { Activity, NutritionRecovery, SyncResult, Workout } from "@/lib/types";

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

/** Why an analysis could not start (POST /analyze, PATCH /context?analyze=true). */
export function analysisErrorMessage(error: Error): string {
  if (!(error instanceof ApiError)) return error.message;
  if (error.status === 503) return "Analisi non disponibile: gli agent sono disattivati su questo server.";
  if (error.status === 429) return "Hai già usato le analisi disponibili per questa corsa.";
  return error.message;
}

export function syncCounts(result: SyncResult) {
  const count = (status: string) => result.items.filter((i) => i.status === status).length;
  return {
    imported: count("IMPORTED"),
    present: count("ALREADY_PRESENT"),
    noFile: count("NO_FILE"),
    failed: count("FAILED"),
  };
}

/** Toast text for an Intervals.icu sync. */
export function syncSummary(result: SyncResult): string {
  const c = syncCounts(result);
  const parts = [
    c.imported && `${c.imported} importate`,
    c.present && `${c.present} già presenti`,
    c.noFile && `${c.noFile} senza file (es. da Strava)`,
    c.failed && `${c.failed} non riuscite`,
  ].filter(Boolean);
  return parts.length ? `Intervals.icu: ${parts.join(", ")}` : "Intervals.icu: nessuna nuova corsa";
}
