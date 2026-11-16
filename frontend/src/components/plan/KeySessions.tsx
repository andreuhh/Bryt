"use client";

import { useMemo, useState } from "react";

import { WorkoutBadges } from "@/components/plan/WorkoutBadges";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { daysBetween, parseDay } from "@/lib/format";
import { workoutVolume } from "@/lib/plan";
import type { Workout } from "@/lib/types";

type Filter = "all" | "long" | "tests";

const monthFmt = new Intl.DateTimeFormat("it-IT", { month: "short" });

function countdown(today: string, day: string): string {
  const d = daysBetween(today, day);
  if (d === 0) return "oggi";
  if (d === 1) return "domani";
  if (d < 0) return "passata";
  if (d < 14) return `tra ${d} giorni`;
  return `tra ${Math.round(d / 7)} settimane`;
}

/** "Where are my long runs": every key session of the plan, upcoming first. */
export function KeySessions({
  workouts,
  today,
  onOpen,
}: {
  workouts: Workout[];
  today: string;
  onOpen: (w: Workout) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [showPast, setShowPast] = useState(false);

  const items = useMemo(
    () =>
      workouts
        .filter((w) => w.is_key_session)
        .filter((w) =>
          filter === "long" ? w.workout_type === "LONG" : filter === "tests" ? w.workout_type === "RACE" : true,
        ),
    [workouts, filter],
  );
  const past = items.filter((w) => w.scheduled_date < today);
  const upcoming = items.filter((w) => w.scheduled_date >= today);
  const shown = showPast ? [...past, ...upcoming] : upcoming;

  return (
    <div className="flex flex-col gap-4">
      <SegmentedControl
        label="Filtra sessioni chiave"
        value={filter}
        onChange={setFilter}
        options={[
          { value: "all", label: "Tutte" },
          { value: "long", label: "Lunghi" },
          { value: "tests", label: "Test e gare" },
        ]}
      />
      <ol className="flex flex-col">
        {shown.map((w) => {
          const date = parseDay(w.scheduled_date);
          const done = w.scheduled_date < today;
          return (
            <li key={w.id}>
              <button
                type="button"
                onClick={() => onOpen(w)}
                className={`flex w-full items-center gap-4 rounded-card px-3 py-3 text-left transition hover:bg-elevated ${
                  done ? "opacity-60" : ""
                }`}
              >
                <span className="flex w-11 shrink-0 flex-col items-center rounded-card bg-elevated py-1.5">
                  <span className="metric text-lg font-bold leading-none">{date.getDate()}</span>
                  <span className="text-[10px] uppercase tracking-wide text-fg-subtle">{monthFmt.format(date)}</span>
                </span>
                <span className="flex min-w-0 flex-1 flex-col gap-1">
                  <span className="truncate text-sm font-medium">{w.title}</span>
                  <span className="flex flex-wrap items-center gap-2 text-xs text-fg-subtle">
                    {countdown(today, w.scheduled_date)}
                    <WorkoutBadges workout={{ ...w, is_key_session: false }} compact />
                  </span>
                </span>
                {workoutVolume(w) && (
                  <span className="metric shrink-0 text-base font-semibold">{workoutVolume(w)}</span>
                )}
              </button>
            </li>
          );
        })}
      </ol>
      {past.length > 0 && (
        <button
          type="button"
          onClick={() => setShowPast((v) => !v)}
          className="self-start text-xs text-fg-muted underline-offset-4 hover:underline"
        >
          {showPast ? "Nascondi le sessioni passate" : `Mostra le ${past.length} sessioni passate`}
        </button>
      )}
    </div>
  );
}
