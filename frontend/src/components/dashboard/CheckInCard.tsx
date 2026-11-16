"use client";

import { useState } from "react";

import { Card } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";
import { useToast } from "@/components/ui/Toast";
import { useSaveCheckIn, useWellness } from "@/lib/queries";

/** Buckets: 5 = "5 h or less", 9 = "9 h or more" (enough for a trend, one tap). */
const SLEEP = [
  { value: 5, label: "≤5" },
  { value: 6, label: "6" },
  { value: 7, label: "7" },
  { value: 8, label: "8" },
  { value: 9, label: "9+" },
];
export const FEELING = [
  { value: 1, emoji: "😫", label: "A pezzi" },
  { value: 2, emoji: "😕", label: "Stanco" },
  { value: 3, emoji: "😐", label: "Normale" },
  { value: 4, emoji: "🙂", label: "Bene" },
  { value: 5, emoji: "😄", label: "Al top" },
];

/**
 * Morning check-in in two taps, saved on each tap. Optional: skipping it costs nothing and the
 * agents treat the day as unknown. Once answered it shrinks to one line.
 */
export function CheckInCard({ today }: { today: string }) {
  const wellness = useWellness(today, today);
  const save = useSaveCheckIn();
  const toast = useToast();
  const [editing, setEditing] = useState(false);

  if (wellness.isPending || wellness.isError) return null;
  const row = wellness.data[0];
  const sleep = row?.sleep_hours ?? null;
  const feeling = row?.feeling ?? null;
  const answer = (patch: { sleep_hours?: number; feeling?: number }) => {
    const next = { day: today, sleep_hours: sleep, feeling, ...patch };
    save.mutate(next, {
      onSuccess: () => next.sleep_hours !== null && next.feeling !== null && setEditing(false),
      onError: (e) => toast(e.message, "error"),
    });
  };

  if (sleep !== null && feeling !== null && !editing) {
    const f = FEELING.find((x) => x.value === feeling);
    return (
      <div className="flex items-center justify-between gap-3 rounded-container border border-line px-5 py-3 text-sm">
        <span className="text-fg-muted">
          Oggi: dormito <span className="metric text-fg">{SLEEP.find((s) => s.value === sleep)?.label ?? sleep} h</span>{" "}
          · <span aria-label={f?.label}>{f?.emoji}</span> {f?.label}
        </span>
        <button type="button" onClick={() => setEditing(true)} className="text-fg-muted hover:text-fg">
          Modifica
        </button>
      </div>
    );
  }

  return (
    <Card className="flex flex-col gap-4">
      <div>
        <h2 className="font-semibold">Come stai oggi?</h2>
        <p className="text-sm text-fg-muted">Due tocchi: il coach ne tiene conto nell&apos;analisi delle corse.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          <p className="text-xs uppercase tracking-wider text-fg-subtle">Ore dormite</p>
          <div role="radiogroup" aria-label="Ore dormite" className="flex gap-1.5">
            {SLEEP.map((s) => (
              <Pill
                key={s.value}
                role="radio"
                aria-checked={sleep === s.value}
                active={sleep === s.value}
                disabled={save.isPending}
                onClick={() => answer({ sleep_hours: s.value })}
                className="metric h-11 flex-1 px-0"
              >
                {s.label}
              </Pill>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <p className="text-xs uppercase tracking-wider text-fg-subtle">Come ti senti</p>
          <div role="radiogroup" aria-label="Come ti senti" className="flex gap-1.5">
            {FEELING.map((f) => (
              <Pill
                key={f.value}
                role="radio"
                aria-checked={feeling === f.value}
                aria-label={f.label}
                title={f.label}
                active={feeling === f.value}
                disabled={save.isPending}
                onClick={() => answer({ feeling: f.value })}
                className="h-11 flex-1 px-0 text-xl"
              >
                {f.emoji}
              </Pill>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}
