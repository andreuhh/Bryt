"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Pill } from "@/components/ui/Pill";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useToast } from "@/components/ui/Toast";
import { SURFACE_LABEL } from "@/lib/dashboard";
import { formatDay, km } from "@/lib/format";
import { activityDay } from "@/lib/dashboard";
import { useAnalyzeInBackground, useSaveContext } from "@/lib/queries";
import type { Activity, ContextTags, Surface } from "@/lib/types";

const SURFACES: Surface[] = ["ASPHALT", "GRAVEL", "TRAIL", "TRACK", "TREADMILL"];
const CAFFEINE = [
  { value: "0", label: "No" },
  { value: "80", label: "1 caffè" },
  { value: "160", label: "2 caffè" },
  { value: "200", label: "Pre-gara / gel" },
] as const;

function nearestCaffeine(mg: number | null | undefined): string {
  if (!mg) return "0";
  return CAFFEINE.reduce((best, c) =>
    Math.abs(Number(c.value) - mg) < Math.abs(Number(best.value) - mg) ? c : best,
  ).value;
}

/**
 * Post-activity quick tags. Saving starts the agent analysis with the full context;
 * skipping (or closing) starts it without tags. Either way it runs exactly once.
 */
export function ContextTagsModal({
  activity,
  onClose,
  onAnalysisStarted,
  title = "Com'è andata?",
}: {
  activity: Activity | null;
  onClose: () => void;
  onAnalysisStarted: (activityId: string) => void;
  title?: string;
}) {
  return (
    <Modal open={activity !== null} onClose={onClose} title={title}>
      {activity && (
        <TagsForm key={activity.id} activity={activity} onClose={onClose} onAnalysisStarted={onAnalysisStarted} />
      )}
    </Modal>
  );
}

function TagsForm({
  activity,
  onClose,
  onAnalysisStarted,
}: {
  activity: Activity;
  onClose: () => void;
  onAnalysisStarted: (id: string) => void;
}) {
  const toast = useToast();
  const save = useSaveContext();
  const skip = useAnalyzeInBackground();
  // Pre-filled with what was saved before (editing from the activity page)
  const saved = activity.context_tags;
  const str = (v: number | null | undefined) => (v === null || v === undefined ? "" : String(v));
  const [surface, setSurface] = useState<Surface>(activity.surface ?? "ASPHALT");
  const [sleepHours, setSleepHours] = useState(str(saved.sleep_hours_prev_night));
  const [sleepQuality, setSleepQuality] = useState(str(saved.sleep_quality));
  const [caffeine, setCaffeine] = useState<string>(nearestCaffeine(saved.caffeine_mg));
  const [caffeineBefore, setCaffeineBefore] = useState(str(saved.caffeine_minutes_before));
  const [rpe, setRpe] = useState(saved.rpe ?? 5);
  const [heat, setHeat] = useState(saved.heat ?? false);
  const [travel, setTravel] = useState(saved.travelled_last_48h ?? false);
  const [jetLag, setJetLag] = useState(str(saved.jet_lag_hours));
  const [unwell, setUnwell] = useState(saved.feeling_unwell ?? false);
  const [notes, setNotes] = useState(saved.notes ?? "");

  const finish = () => {
    onAnalysisStarted(activity.id);
    onClose();
  };

  const submit = () => {
    const tags: ContextTags = {
      sleep_hours_prev_night: sleepHours ? Number(sleepHours) : null,
      sleep_quality: sleepQuality ? Number(sleepQuality) : null,
      caffeine_mg: Number(caffeine) || null,
      caffeine_minutes_before: Number(caffeine) && caffeineBefore ? Number(caffeineBefore) : null,
      rpe,
      heat,
      travelled_last_48h: travel,
      jet_lag_hours: travel && jetLag ? Number(jetLag) : null,
      feeling_unwell: unwell,
      notes: notes.trim() || null,
    };
    save.mutate(
      { id: activity.id, body: { surface, context_tags: tags } },
      {
        onSuccess: () => {
          toast("Contesto salvato: gli agent stanno analizzando la corsa", "success");
          finish();
        },
        onError: (e) => toast(e.message, "error"),
      },
    );
  };

  const skipTags = () =>
    skip.mutate(activity.id, {
      onSuccess: () => {
        toast("Analisi avviata senza tag", "neutral");
        finish();
      },
      onError: (e) => toast(e.message, "error"),
    });

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-fg-muted first-letter:uppercase">
        {formatDay(activityDay(activity))} · {km(activity.distance_m)} km. Due domande per evitare falsi allarmi:
        caffè, sonno e caldo spiegano spesso una frequenza cardiaca alta.
      </p>

      <Field label="Superficie">
        <SegmentedControl
          label="Superficie"
          value={surface}
          onChange={setSurface}
          options={SURFACES.map((s) => ({ value: s, label: SURFACE_LABEL[s] }))}
        />
      </Field>

      <div className="grid gap-6 sm:grid-cols-[minmax(0,1fr)_auto]">
        <Field label="Ore di sonno stanotte">
          <input
            type="number"
            inputMode="decimal"
            min={0}
            max={14}
            step={0.5}
            value={sleepHours}
            onChange={(e) => setSleepHours(e.target.value)}
            placeholder="es. 7,5"
            className="h-11 w-full rounded-card border border-line bg-elevated px-4 text-sm text-fg placeholder:text-fg-subtle focus:border-line-strong focus:outline-none"
          />
        </Field>
        <Field label="Qualità del sonno">
          <div className="flex gap-1.5" role="radiogroup" aria-label="Qualità del sonno (1-5)">
            {["1", "2", "3", "4", "5"].map((v) => (
              <Pill
                key={v}
                role="radio"
                aria-checked={sleepQuality === v}
                active={sleepQuality === v}
                onClick={() => setSleepQuality(sleepQuality === v ? "" : v)}
                className="size-11 px-0"
              >
                {v}
              </Pill>
            ))}
          </div>
        </Field>
      </div>

      <Field label="Caffeina prima della corsa">
        <SegmentedControl
          label="Caffeina"
          value={caffeine}
          onChange={setCaffeine}
          options={CAFFEINE.map((c) => ({ value: c.value, label: c.label }))}
        />
        {caffeine !== "0" && (
          <input
            type="number"
            inputMode="numeric"
            min={0}
            max={600}
            value={caffeineBefore}
            onChange={(e) => setCaffeineBefore(e.target.value)}
            placeholder="Quanti minuti prima?"
            className="mt-2 h-11 w-full rounded-card border border-line bg-elevated px-4 text-sm text-fg placeholder:text-fg-subtle focus:border-line-strong focus:outline-none"
          />
        )}
      </Field>

      <Field label={`Fatica percepita (RPE): ${rpe}/10`}>
        <input
          type="range"
          min={1}
          max={10}
          value={rpe}
          onChange={(e) => setRpe(Number(e.target.value))}
          className="w-full accent-[var(--bryt-accent-pace)]"
          aria-label="Fatica percepita"
        />
      </Field>

      <Field label="Altro">
        <div className="flex flex-wrap gap-2">
          <Pill active={heat} aria-pressed={heat} onClick={() => setHeat((v) => !v)}>
            Caldo
          </Pill>
          <Pill active={travel} aria-pressed={travel} onClick={() => setTravel((v) => !v)}>
            Viaggio nelle ultime 48 h
          </Pill>
          <Pill active={unwell} aria-pressed={unwell} onClick={() => setUnwell((v) => !v)}>
            Non stavo bene
          </Pill>
        </div>
        {travel && (
          <input
            type="number"
            inputMode="numeric"
            min={-12}
            max={14}
            value={jetLag}
            onChange={(e) => setJetLag(e.target.value)}
            placeholder="Fuso orario: ore di differenza (es. -6 da New York)"
            className="mt-2 h-11 w-full rounded-card border border-line bg-elevated px-4 text-sm text-fg placeholder:text-fg-subtle focus:border-line-strong focus:outline-none"
          />
        )}
      </Field>

      <Field label="Note (facoltative)">
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          maxLength={1000}
          placeholder="es. polpacci duri dal km 15"
          className="w-full rounded-card border border-line bg-elevated px-4 py-3 text-sm text-fg placeholder:text-fg-subtle focus:border-line-strong focus:outline-none"
        />
      </Field>

      <div className="flex flex-col gap-2 sm:flex-row-reverse">
        <Button onClick={submit} loading={save.isPending} disabled={skip.isPending}>
          Salva e analizza
        </Button>
        <Button variant="ghost" onClick={skipTags} loading={skip.isPending} disabled={save.isPending}>
          Salta, analizza senza tag
        </Button>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium uppercase tracking-wider text-fg-subtle">{label}</p>
      {children}
    </div>
  );
}
