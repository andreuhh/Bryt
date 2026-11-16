/** Italian formatting for telemetry. Client-side only (dates depend on the browser clock). */

const TZ = "Europe/Rome";

export function pace(secondsPerKm: number | null | undefined): string {
  if (!secondsPerKm) return "–";
  const total = Math.round(secondsPerKm);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function paceRange(range: { fast_s_per_km: number; slow_s_per_km: number } | null | undefined) {
  return range ? `${pace(range.fast_s_per_km)}–${pace(range.slow_s_per_km)}` : null;
}

export function duration(seconds: number | null | undefined): string {
  if (!seconds) return "–";
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h ? `${h}h${String(m).padStart(2, "0")}` : `${m}'`;
}

export function km(meters: number | null | undefined, digits = 1): string {
  if (!meters) return "–";
  const value = meters / 1000;
  return Number.isInteger(value) ? String(value) : value.toFixed(digits).replace(".", ",");
}

/** "2026-11-17" → Date at local midnight (no UTC shift). */
export function parseDay(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function isoDay(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function today(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date());
}

export function addDays(iso: string, days: number): string {
  const date = parseDay(iso);
  date.setDate(date.getDate() + days);
  return isoDay(date);
}

export function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((parseDay(toIso).getTime() - parseDay(fromIso).getTime()) / 86_400_000);
}

export function mondayOf(iso: string): string {
  const day = parseDay(iso).getDay(); // 0 = Sunday
  return addDays(iso, -((day + 6) % 7));
}

const dayFmt = new Intl.DateTimeFormat("it-IT", { weekday: "short", day: "numeric", month: "short" });
const shortFmt = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "short" });
const weekdayFmt = new Intl.DateTimeFormat("it-IT", { weekday: "short" });
const longFmt = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "long", year: "numeric" });

export const formatDay = (iso: string) => dayFmt.format(parseDay(iso));
export const formatShort = (iso: string) => shortFmt.format(parseDay(iso));
export const formatWeekday = (iso: string) => weekdayFmt.format(parseDay(iso));
export const formatLong = (iso: string) => longFmt.format(parseDay(iso));
