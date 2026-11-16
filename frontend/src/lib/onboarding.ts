/** Onboarding wizard: draft model, conversions to the API payload, per-step validation. */

import type {
  AthleteBackground,
  Methodology,
  OnboardingPayload,
  PersonalBest,
  Profile,
  Surface,
  User,
  Weekday,
} from "@/lib/types";

export type Hms = { h: string; m: string; s: string };

export type PbDraft = {
  key: string;
  distance: string; // preset meters as string, or "custom"
  customKm: string;
  time: Hms;
  achieved_on: string;
  surface: Surface;
  event_name: string;
};

/** Usual surface of a generic watch "Run" (trail, track and treadmill have their own modes). */
export type RunSurface = "ASPHALT" | "GRAVEL" | "MIXED";
export const RUN_SURFACE_OPTIONS: { value: RunSurface; label: string }[] = [
  { value: "ASPHALT", label: "Asfalto" },
  { value: "GRAVEL", label: "Sterrato" },
  { value: "MIXED", label: "Misto" },
];
export const RUN_SURFACE_HINT =
  "Asfalto: strade e ciclabili. Sterrato: ghiaia, campagna, parchi. Misto: un po' e un po'. Il trail e la pista li riconosciamo dalla modalità dell'orologio.";
const isRunSurface = (s: Surface | null | undefined): s is RunSurface =>
  s === "ASPHALT" || s === "GRAVEL" || s === "MIXED";

export type Draft = {
  display_name: string;
  background: AthleteBackground | "";
  birth_year: string;
  weight_kg: string;
  threshold_hr: string;
  max_hr: string;
  resting_hr: string;
  pbs: PbDraft[];
  has_race: boolean;
  race_name: string;
  race_date: string;
  race_distance: string;
  race_custom_km: string;
  race_time: Hms;
  race_surface: Surface;
  preferred_slot: "MORNING" | "LUNCH" | "EVENING" | "";
  available_days: Weekday[];
  work_type: "SEDENTARY" | "PHYSICAL" | "";
  avg_sleep_hours: string;
  terrain_access: Surface[];
  default_run_surface: RunSurface | "";
  weekly_volume_km: string;
  peak_volume_km: string;
  strength_setting: "NONE" | "HOME" | "GYM" | "";
  strength_sessions: "0" | "1" | "2" | "";
  double_sessions_ok: "yes" | "no" | "";
  long_run_day: Weekday | "";
  hr_sensor: "CHEST_STRAP" | "WRIST_OPTICAL" | "";
  injury_notes: string;
  coach_notes: string;
  methodology: Methodology;
  intervals_athlete_id: string;
  intervals_api_key: string; // never persisted in the browser
};

export const DISTANCES = [
  { value: "5000", label: "5 km" },
  { value: "10000", label: "10 km" },
  { value: "21097", label: "Mezza" },
  { value: "42195", label: "Maratona" },
  { value: "custom", label: "Altra" },
] as const;

export const WEEKDAYS: { value: Weekday; label: string }[] = [
  { value: "MON", label: "Lun" },
  { value: "TUE", label: "Mar" },
  { value: "WED", label: "Mer" },
  { value: "THU", label: "Gio" },
  { value: "FRI", label: "Ven" },
  { value: "SAT", label: "Sab" },
  { value: "SUN", label: "Dom" },
];

export const emptyHms = (): Hms => ({ h: "", m: "", s: "" });

export const newPb = (): PbDraft => ({
  key: Math.random().toString(36).slice(2),
  distance: "10000",
  customKm: "",
  time: emptyHms(),
  achieved_on: "",
  surface: "ASPHALT",
  event_name: "",
});

export const EMPTY_DRAFT: Draft = {
  display_name: "",
  background: "",
  birth_year: "",
  weight_kg: "",
  threshold_hr: "",
  max_hr: "",
  resting_hr: "",
  pbs: [newPb()],
  has_race: true,
  race_name: "",
  race_date: "",
  race_distance: "42195",
  race_custom_km: "",
  race_time: emptyHms(),
  race_surface: "ASPHALT",
  preferred_slot: "",
  available_days: [],
  work_type: "",
  avg_sleep_hours: "",
  terrain_access: [],
  default_run_surface: "",
  weekly_volume_km: "",
  peak_volume_km: "",
  strength_setting: "",
  strength_sessions: "",
  double_sessions_ok: "",
  long_run_day: "",
  hr_sensor: "",
  injury_notes: "",
  coach_notes: "",
  methodology: "TRADITIONAL",
  intervals_athlete_id: "",
  intervals_api_key: "",
};

// --- Conversions ----------------------------------------------------------------------

export const hmsToSeconds = (t: Hms) => (Number(t.h) || 0) * 3600 + (Number(t.m) || 0) * 60 + (Number(t.s) || 0);

export function secondsToHms(total: number | null | undefined): Hms {
  if (!total) return emptyHms();
  return { h: String(Math.floor(total / 3600)), m: String(Math.floor((total % 3600) / 60)), s: String(total % 60) };
}

function meters(preset: string, customKm: string): number | null {
  if (preset === "custom") return customKm ? Math.round(Number(customKm.replace(",", ".")) * 1000) : null;
  return Number(preset) || null;
}

const presetFor = (m: number | null | undefined) =>
  DISTANCES.some((d) => d.value === String(m)) ? String(m) : m ? "custom" : "42195";

const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));
const str = (v: number | null | undefined) => (v === null || v === undefined ? "" : String(v));

export function fromProfile(profile: Profile, user: User | undefined): Draft {
  return {
    ...EMPTY_DRAFT,
    display_name: user?.display_name ?? "",
    background: profile.background,
    birth_year: str(profile.birth_year),
    weight_kg: str(profile.weight_kg),
    threshold_hr: str(profile.threshold_hr),
    max_hr: str(profile.max_hr),
    resting_hr: str(profile.resting_hr),
    pbs: [], // saved ones are shown read-only; the wizard only adds new results
    has_race: Boolean(profile.target_race_date),
    race_name: profile.target_race_name ?? "",
    race_date: profile.target_race_date ?? "",
    race_distance: presetFor(profile.target_race_distance_m),
    race_custom_km:
      presetFor(profile.target_race_distance_m) === "custom" ? String((profile.target_race_distance_m ?? 0) / 1000) : "",
    race_time: secondsToHms(profile.target_race_time_s),
    race_surface: profile.target_race_surface ?? "ASPHALT",
    preferred_slot: profile.preferred_slot,
    available_days: profile.available_days,
    work_type: profile.work_type,
    avg_sleep_hours: str(profile.avg_sleep_hours),
    terrain_access: profile.terrain_access,
    default_run_surface: isRunSurface(profile.default_run_surface) ? profile.default_run_surface : "",
    weekly_volume_km: str(profile.weekly_volume_km),
    peak_volume_km: str(profile.peak_volume_km),
    strength_setting: profile.strength_setting,
    strength_sessions: String(Math.min(profile.strength_sessions_per_week, 2)) as Draft["strength_sessions"],
    double_sessions_ok: profile.double_sessions_ok ? "yes" : "no",
    long_run_day: profile.long_run_day ?? "",
    hr_sensor: profile.hr_sensor ?? "",
    injury_notes: profile.injury_notes ?? "",
    coach_notes: profile.coach_notes ?? "",
    methodology: profile.methodology,
    intervals_athlete_id: profile.intervals_athlete_id ?? "",
  };
}

export function toPayload(d: Draft): OnboardingPayload {
  const withKey = d.intervals_api_key.trim() !== "";
  return {
    display_name: d.display_name.trim() || null,
    timezone: "Europe/Rome",
    profile: {
      background: d.background as AthleteBackground,
      birth_year: num(d.birth_year),
      weight_kg: num(d.weight_kg),
      threshold_hr: num(d.threshold_hr),
      max_hr: num(d.max_hr),
      resting_hr: num(d.resting_hr),
      weekly_volume_km: Number(d.weekly_volume_km.replace(",", ".")),
      peak_volume_km: num(d.peak_volume_km),
      target_race_name: d.has_race ? d.race_name.trim() || null : null,
      target_race_date: d.has_race ? d.race_date || null : null,
      target_race_distance_m: d.has_race ? meters(d.race_distance, d.race_custom_km) : null,
      target_race_time_s: d.has_race ? hmsToSeconds(d.race_time) || null : null,
      target_race_surface: d.has_race ? d.race_surface : null,
      preferred_slot: d.preferred_slot as "MORNING",
      available_days: d.available_days,
      work_type: d.work_type as "SEDENTARY",
      avg_sleep_hours: num(d.avg_sleep_hours),
      default_run_surface: d.default_run_surface || null,
      terrain_access: d.terrain_access,
      methodology: d.methodology,
      double_sessions_ok: d.double_sessions_ok === "yes",
      long_run_day: d.long_run_day || null,
      strength_sessions_per_week: Number(d.strength_sessions) || 0,
      strength_setting: d.strength_setting as "NONE",
      hr_sensor: d.hr_sensor || null,
      injury_notes: d.injury_notes.trim() || null,
      coach_notes: d.coach_notes.trim() || null,
      // Write-only key: sent only when typed; otherwise the stored connection is kept
      intervals_athlete_id: withKey ? d.intervals_athlete_id.trim() : null,
      intervals_api_key: withKey ? d.intervals_api_key.trim() : null,
    },
    personal_bests: d.pbs.map((pb) => ({
      distance_m: meters(pb.distance, pb.customKm) ?? 0,
      time_s: hmsToSeconds(pb.time),
      achieved_on: pb.achieved_on,
      surface: pb.surface,
      event_name: pb.event_name.trim() || null,
    })),
  };
}

// --- Validation -----------------------------------------------------------------------

export type Errors = Partial<Record<string, string>>;

const inRange = (v: string, min: number, max: number) => {
  const n = num(v);
  return n === null || (n >= min && n <= max);
};

export function validateStep(step: number, d: Draft, savedPbs: PersonalBest[], today: string): Errors {
  const e: Errors = {};
  if (step === 0) {
    if (!d.background) e.background = "Scegli il tuo background";
    if (!inRange(d.birth_year, 1920, 2020)) e.birth_year = "Anno non valido";
    if (!inRange(d.weight_kg, 30, 200)) e.weight_kg = "Peso non valido";
    const rest = num(d.resting_hr), thr = num(d.threshold_hr), max = num(d.max_hr);
    if (rest && thr && rest >= thr) e.resting_hr = "Deve essere più bassa della FC di soglia";
    if (thr && max && thr >= max) e.threshold_hr = "Deve essere più bassa della FC max";
  }
  if (step === 1) {
    if (d.pbs.length === 0 && savedPbs.length === 0)
      e.pbs = "Serve almeno un risultato: le tue zone di passo si calcolano da qui";
    d.pbs.forEach((pb, i) => {
      if (!meters(pb.distance, pb.customKm) || (meters(pb.distance, pb.customKm) ?? 0) < 1500)
        e[`pb${i}.distance`] = "Distanza di almeno 1,5 km";
      if (hmsToSeconds(pb.time) <= 0) e[`pb${i}.time`] = "Inserisci il tempo";
      if (!pb.achieved_on) e[`pb${i}.date`] = "Inserisci la data (anche approssimativa)";
      else if (pb.achieved_on > today) e[`pb${i}.date`] = "Data nel futuro";
    });
  }
  if (step === 2 && d.has_race) {
    if (!d.race_date) e.race_date = "Inserisci la data della gara";
    else if (d.race_date <= today) e.race_date = "La gara deve essere nel futuro";
    if (!meters(d.race_distance, d.race_custom_km)) e.race_distance = "Inserisci la distanza";
  }
  if (step === 3) {
    if (!d.preferred_slot) e.preferred_slot = "Quando corri di solito?";
    if (d.available_days.length === 0) e.available_days = "Scegli almeno un giorno";
    if (!d.work_type) e.work_type = "Scegli il tipo di lavoro";
    if (d.terrain_access.length === 0) e.terrain_access = "Scegli almeno un terreno";
    if (!d.default_run_surface) e.default_run_surface = "Su cosa corri di solito?";
    if (!inRange(d.avg_sleep_hours, 0, 14)) e.avg_sleep_hours = "Valore non valido";
  }
  if (step === 4) {
    if (d.weekly_volume_km.trim() === "") e.weekly_volume_km = "Quanti km corri di solito a settimana?";
    else if (!inRange(d.weekly_volume_km, 0, 300)) e.weekly_volume_km = "Valore non valido";
    if (!inRange(d.peak_volume_km, 0, 300)) e.peak_volume_km = "Valore non valido";
    if (!d.strength_setting) e.strength_setting = "Dove puoi fare forza?";
    if (!d.strength_sessions) e.strength_sessions = "Quante volte la fai oggi?";
    if (!d.double_sessions_ok) e.double_sessions_ok = "Rispondi sì o no";
  }
  if (step === 5) {
    const id = d.intervals_athlete_id.trim(), key = d.intervals_api_key.trim();
    if (key && !/^i\d+$/.test(id)) e.intervals_athlete_id = "L'Athlete ID ha la forma i12345";
  }
  return e;
}

// --- Draft persistence (per-browser convenience; never stores the API key) -------------

const DRAFT_KEY = "bryt-onboarding-draft";

export function loadDraft(): Draft | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    return raw ? { ...EMPTY_DRAFT, ...JSON.parse(raw), intervals_api_key: "" } : null;
  } catch {
    return null;
  }
}

export function saveDraft(d: Draft) {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ ...d, intervals_api_key: "" }));
  } catch {
    /* storage unavailable: the wizard still works, just without resume */
  }
}

export function clearDraft() {
  try {
    localStorage.removeItem(DRAFT_KEY);
  } catch {
    /* ignore */
  }
}
