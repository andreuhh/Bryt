"use client";

import { IconX } from "@/components/icons";
import { Button } from "@/components/ui/Button";
import { DurationInput, Field, MultiPills, NumberInput, TextArea, TextInput } from "@/components/ui/Field";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { SURFACE_LABEL } from "@/lib/dashboard";
import { formatLong, km as kmFmt } from "@/lib/format";
import {
  DISTANCES,
  type Draft,
  type Errors,
  newPb,
  type PbDraft,
  RUN_SURFACE_HINT,
  RUN_SURFACE_OPTIONS,
  WEEKDAYS,
} from "@/lib/onboarding";
import type { PersonalBest, Surface } from "@/lib/types";

export type StepProps = { d: Draft; set: (patch: Partial<Draft>) => void; errors: Errors };

const SURFACES: Surface[] = ["ASPHALT", "GRAVEL", "TRAIL", "TRACK", "TREADMILL"];
const surfaceOptions = SURFACES.map((s) => ({ value: s, label: SURFACE_LABEL[s] }));

// --- 1. Athlete ---------------------------------------------------------------------------

export function StepAthlete({ d, set, errors }: StepProps) {
  return (
    <div className="flex flex-col gap-6">
      <Field label="Nome">
        <TextInput value={d.display_name} onChange={(e) => set({ display_name: e.target.value })} placeholder="Nome" />
      </Field>
      <Field label="Il tuo background" required error={errors.background}>
        <SegmentedControl
          label="Background"
          value={d.background}
          onChange={(background) => set({ background })}
          options={[
            { value: "ROAD", label: "Strada" },
            { value: "TRAIL", label: "Trail" },
            { value: "TRACK", label: "Pista / mezzofondo" },
          ]}
        />
      </Field>
      <div className="grid gap-6 sm:grid-cols-2">
        <Field label="Anno di nascita" error={errors.birth_year}>
          <NumberInput value={d.birth_year} onChange={(e) => set({ birth_year: e.target.value })} placeholder="es. 1992" invalid={!!errors.birth_year} />
        </Field>
        <Field label="Peso (kg)" error={errors.weight_kg} hint="Serve per i grammi di carboidrati e proteine.">
          <NumberInput value={d.weight_kg} onChange={(e) => set({ weight_kg: e.target.value })} placeholder="es. 63" invalid={!!errors.weight_kg} />
        </Field>
      </div>
      <div className="flex flex-col gap-3 rounded-card bg-elevated/50 p-4">
        <div className="grid gap-6 sm:grid-cols-3">
          <Field label="FC soglia" error={errors.threshold_hr}>
            <NumberInput value={d.threshold_hr} onChange={(e) => set({ threshold_hr: e.target.value })} placeholder="bpm" invalid={!!errors.threshold_hr} />
          </Field>
          <Field label="FC max">
            <NumberInput value={d.max_hr} onChange={(e) => set({ max_hr: e.target.value })} placeholder="bpm" />
          </Field>
          <Field label="FC a riposo" error={errors.resting_hr}>
            <NumberInput value={d.resting_hr} onChange={(e) => set({ resting_hr: e.target.value })} placeholder="bpm" invalid={!!errors.resting_hr} />
          </Field>
        </div>
        <p className="text-sm text-fg-muted">
          Frequenza cardiaca: se non la conosci lascia vuoto. Le zone di passo si calcolano comunque dai tuoi
          risultati e potrai aggiungerla in seguito.
        </p>
      </div>
    </div>
  );
}

// --- 2. Results / PBs ---------------------------------------------------------------------

export function StepResults({ d, set, errors, saved }: StepProps & { saved: PersonalBest[] }) {
  const update = (key: string, patch: Partial<PbDraft>) =>
    set({ pbs: d.pbs.map((pb) => (pb.key === key ? { ...pb, ...patch } : pb)) });

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-fg-muted">
        I tuoi primati e le gare recenti, anche non record. Più sono recenti, più le zone sono precise. Se non
        ricordi il giorno esatto, metti il 15 del mese.
      </p>

      {saved.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium uppercase tracking-wider text-fg-subtle">Già salvati</p>
          <ul className="flex flex-col gap-1 text-sm">
            {saved.map((pb) => (
              <li key={pb.id} className="metric flex justify-between rounded-card bg-elevated px-4 py-2 text-fg-muted">
                <span>
                  {pb.event_name ?? `${kmFmt(pb.distance_m)} km`} · {formatLong(pb.achieved_on)}
                </span>
                <span className="text-fg">{secondsLabel(pb.time_s)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {d.pbs.map((pb, i) => (
        <div key={pb.key} className="flex flex-col gap-4 rounded-card border border-line p-4">
          <div className="flex items-start justify-between gap-3">
            <Field label="Distanza" required error={errors[`pb${i}.distance`]}>
              <SegmentedControl
                label="Distanza"
                value={pb.distance}
                onChange={(distance) => update(pb.key, { distance })}
                options={DISTANCES.map((x) => ({ value: x.value, label: x.label }))}
              />
              {pb.distance === "custom" && (
                <NumberInput
                  value={pb.customKm}
                  onChange={(e) => update(pb.key, { customKm: e.target.value })}
                  placeholder="km, es. 15"
                  className="max-w-40"
                />
              )}
            </Field>
            <button
              type="button"
              aria-label="Rimuovi risultato"
              onClick={() => set({ pbs: d.pbs.filter((x) => x.key !== pb.key) })}
              className="rounded-pill p-2 text-fg-subtle hover:bg-elevated hover:text-fg"
            >
              <IconX width={16} height={16} />
            </button>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Tempo" required error={errors[`pb${i}.time`]}>
              <DurationInput label="Tempo" value={pb.time} onChange={(time) => update(pb.key, { time })} invalid={!!errors[`pb${i}.time`]} />
            </Field>
            <Field label="Data" required error={errors[`pb${i}.date`]}>
              <TextInput
                type="date"
                value={pb.achieved_on}
                onChange={(e) => update(pb.key, { achieved_on: e.target.value })}
                invalid={!!errors[`pb${i}.date`]}
              />
            </Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Superficie">
              <SegmentedControl label="Superficie" value={pb.surface} onChange={(surface) => update(pb.key, { surface })} options={surfaceOptions.slice(0, 3)} />
            </Field>
            <Field label="Nome della gara">
              <TextInput value={pb.event_name} onChange={(e) => update(pb.key, { event_name: e.target.value })} placeholder="es. Maratona di Valencia" />
            </Field>
          </div>
        </div>
      ))}

      {errors.pbs && <p className="text-sm text-accent-load">{errors.pbs}</p>}
      <Button variant="secondary" size="sm" className="self-start" onClick={() => set({ pbs: [...d.pbs, newPb()] })}>
        + Aggiungi un risultato
      </Button>
    </div>
  );
}

function secondsLabel(s: number) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return `${h ? `${h}:` : ""}${String(m).padStart(h ? 2 : 1, "0")}:${String(sec).padStart(2, "0")}`;
}

// --- 3. Goal ------------------------------------------------------------------------------

export function StepGoal({ d, set, errors }: StepProps) {
  return (
    <div className="flex flex-col gap-6">
      <SegmentedControl
        label="Hai una gara obiettivo?"
        value={d.has_race ? "yes" : "no"}
        onChange={(v) => set({ has_race: v === "yes" })}
        options={[
          { value: "yes", label: "Ho una gara obiettivo" },
          { value: "no", label: "Nessuna gara: piano di 12 settimane per crescere, con test finale" },
        ]}
      />
      {d.has_race && (
        <>
          <Field label="Nome della gara">
            <TextInput value={d.race_name} onChange={(e) => set({ race_name: e.target.value })} placeholder="es. Milano Marathon" />
          </Field>
          <div className="grid gap-6 sm:grid-cols-2">
            <Field label="Data" required error={errors.race_date}>
              <TextInput type="date" value={d.race_date} onChange={(e) => set({ race_date: e.target.value })} invalid={!!errors.race_date} />
            </Field>
            <Field label="Tempo obiettivo" hint="Lascialo vuoto se non hai un obiettivo cronometrico.">
              <DurationInput label="Tempo obiettivo" value={d.race_time} onChange={(race_time) => set({ race_time })} />
            </Field>
          </div>
          <Field label="Distanza" required error={errors.race_distance}>
            <SegmentedControl
              label="Distanza"
              value={d.race_distance}
              onChange={(race_distance) => set({ race_distance })}
              options={DISTANCES.map((x) => ({ value: x.value, label: x.label }))}
            />
            {d.race_distance === "custom" && (
              <NumberInput value={d.race_custom_km} onChange={(e) => set({ race_custom_km: e.target.value })} placeholder="km" className="max-w-40" />
            )}
          </Field>
          <Field label="Superficie della gara">
            <SegmentedControl label="Superficie" value={d.race_surface} onChange={(race_surface) => set({ race_surface })} options={surfaceOptions.slice(0, 3)} />
          </Field>
        </>
      )}
    </div>
  );
}

// --- 4. Lifestyle -------------------------------------------------------------------------

export function StepLifestyle({ d, set, errors }: StepProps) {
  return (
    <div className="flex flex-col gap-6">
      <Field label="Quando corri di solito" required error={errors.preferred_slot}>
        <SegmentedControl
          label="Fascia oraria"
          value={d.preferred_slot}
          onChange={(preferred_slot) => set({ preferred_slot })}
          options={[
            { value: "MORNING", label: "Mattina" },
            { value: "LUNCH", label: "Pausa pranzo" },
            { value: "EVENING", label: "Sera" },
          ]}
        />
      </Field>
      <Field label="Giorni in cui puoi correre" required error={errors.available_days}>
        <MultiPills label="Giorni disponibili" options={WEEKDAYS} value={d.available_days} onChange={(available_days) => set({ available_days })} />
      </Field>
      <div className="grid gap-6 sm:grid-cols-2">
        <Field label="Lavoro" required error={errors.work_type}>
          <SegmentedControl
            label="Lavoro"
            value={d.work_type}
            onChange={(work_type) => set({ work_type })}
            options={[
              { value: "SEDENTARY", label: "Sedentario" },
              { value: "PHYSICAL", label: "Fisico" },
            ]}
          />
        </Field>
        <Field label="Ore di sonno medie" error={errors.avg_sleep_hours}>
          <NumberInput value={d.avg_sleep_hours} onChange={(e) => set({ avg_sleep_hours: e.target.value })} placeholder="es. 7" step={0.5} />
        </Field>
      </div>
      <Field label="Terreni a cui hai accesso" required error={errors.terrain_access}>
        <MultiPills label="Terreni" options={surfaceOptions} value={d.terrain_access} onChange={(terrain_access) => set({ terrain_access })} />
      </Field>
      <Field
        label="Quando scegli “Corsa” sull'orologio, di solito corri su"
        required
        error={errors.default_run_surface}
        hint={RUN_SURFACE_HINT}
      >
        <SegmentedControl
          label="Superficie abituale"
          value={d.default_run_surface}
          onChange={(default_run_surface) => set({ default_run_surface })}
          options={RUN_SURFACE_OPTIONS}
        />
      </Field>
    </div>
  );
}

// --- 5. Training --------------------------------------------------------------------------

export function StepTraining({ d, set, errors }: StepProps) {
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 sm:grid-cols-2">
        <Field label="Km a settimana, di solito" required error={errors.weekly_volume_km} hint="Media delle ultime 8-12 settimane.">
          <NumberInput value={d.weekly_volume_km} onChange={(e) => set({ weekly_volume_km: e.target.value })} placeholder="es. 70" invalid={!!errors.weekly_volume_km} />
        </Field>
        <Field label="Settimana più alta mai fatta" error={errors.peak_volume_km} hint="Il volume massimo della tua ultima preparazione.">
          <NumberInput value={d.peak_volume_km} onChange={(e) => set({ peak_volume_km: e.target.value })} placeholder="es. 82" />
        </Field>
      </div>
      <div className="grid gap-6 sm:grid-cols-2">
        <Field label="Dove puoi fare forza" required error={errors.strength_setting}>
          <SegmentedControl
            label="Forza"
            value={d.strength_setting}
            onChange={(strength_setting) => set({ strength_setting })}
            options={[
              { value: "NONE", label: "Da nessuna parte" },
              { value: "HOME", label: "A casa" },
              { value: "GYM", label: "In palestra" },
            ]}
          />
        </Field>
        <Field label="Quante volte la fai oggi" required error={errors.strength_sessions}>
          <SegmentedControl
            label="Sedute di forza a settimana"
            value={d.strength_sessions}
            onChange={(strength_sessions) => set({ strength_sessions })}
            options={[
              { value: "0", label: "Mai" },
              { value: "1", label: "1 a settimana" },
              { value: "2", label: "2 o più" },
            ]}
          />
        </Field>
      </div>
      <div className="grid gap-6 sm:grid-cols-2">
        <Field label="Puoi correre due volte nello stesso giorno?" required error={errors.double_sessions_ok} hint="Serve per le doppie soglie (mattina e sera).">
          <SegmentedControl
            label="Doppie sedute"
            value={d.double_sessions_ok}
            onChange={(double_sessions_ok) => set({ double_sessions_ok })}
            options={[
              { value: "yes", label: "Sì" },
              { value: "no", label: "No" },
            ]}
          />
        </Field>
        <Field label="Giorno preferito per il lungo">
          <SegmentedControl label="Giorno del lungo" value={d.long_run_day} onChange={(long_run_day) => set({ long_run_day })} options={WEEKDAYS} />
        </Field>
      </div>
      <Field label="Frequenza cardiaca rilevata con" hint="La fascia cardio è più affidabile del sensore al polso.">
        <SegmentedControl
          label="Sensore FC"
          value={d.hr_sensor}
          onChange={(hr_sensor) => set({ hr_sensor })}
          options={[
            { value: "CHEST_STRAP", label: "Fascia cardio" },
            { value: "WRIST_OPTICAL", label: "Sensore al polso" },
          ]}
        />
      </Field>
      <Field label="Infortuni ricorrenti">
        <TextArea rows={2} maxLength={1000} value={d.injury_notes} onChange={(e) => set({ injury_notes: e.target.value })} placeholder="es. tendine d'Achille sinistro sotto carico" />
      </Field>
      <Field label="Note per il coach" hint="Com'è andata l'ultima gara, rifornimenti, vincoli: gli agent leggono tutto.">
        <TextArea rows={3} maxLength={2000} value={d.coach_notes} onChange={(e) => set({ coach_notes: e.target.value })} placeholder="es. alla maratona i quadricipiti hanno ceduto dopo il km 25" />
      </Field>
    </div>
  );
}

// --- 6. Methodology & Intervals -----------------------------------------------------------

const METHODS = [
  { value: "TRADITIONAL", title: "Tradizionale", body: "Distribuzione polarizzata: tanta corsa facile, poche sedute di qualità ben dosate." },
  { value: "DOUBLE_THRESHOLD", title: "Doppia soglia", body: "Scuola norvegese: soglia mattina e sera nello stesso giorno, a intensità controllata." },
  { value: "BLOCK", title: "A blocchi", body: "Carico concentrato per alcuni giorni, poi assorbimento: per chi regge picchi di lavoro." },
] as const;

export function StepMethod({ d, set, errors }: StepProps) {
  return (
    <div className="flex flex-col gap-6">
      <Field label="Metodologia">
        <div role="radiogroup" aria-label="Metodologia" className="grid gap-3 sm:grid-cols-3">
          {METHODS.map((m) => {
            const on = d.methodology === m.value;
            return (
              <button
                key={m.value}
                type="button"
                role="radio"
                aria-checked={on}
                onClick={() => set({ methodology: m.value })}
                className={`flex flex-col gap-1 rounded-card border p-4 text-left transition ${on ? "border-fg bg-elevated" : "border-line hover:bg-elevated/60"
                  }`}
              >
                <span className="font-semibold">{m.title}</span>
                <span className="text-xs text-fg-muted">{m.body}</span>
              </button>
            );
          })}
        </div>
      </Field>

      <div className="flex flex-col gap-4 rounded-card border border-line p-4">
        <div>
          <p className="font-semibold">Intervals.icu</p>
          <p className="text-sm text-fg-muted">
            Facoltativo e gratuito: importa in automatico le corse da Garmin, Coros, Suunto, Polar. Trovi i dati in
            Intervals.icu → Settings → Developer Settings. Puoi anche caricare i file a mano.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Athlete ID" error={errors.intervals_athlete_id}>
            <TextInput value={d.intervals_athlete_id} onChange={(e) => set({ intervals_athlete_id: e.target.value })} placeholder="i12345" invalid={!!errors.intervals_athlete_id} />
          </Field>
          <Field label="API Key" hint="Viene verificata e salvata cifrata. Lasciala vuota per non cambiare il collegamento attuale.">
            <TextInput type="password" autoComplete="off" value={d.intervals_api_key} onChange={(e) => set({ intervals_api_key: e.target.value })} placeholder="••••••••" />
          </Field>
        </div>
      </div>
    </div>
  );
}
