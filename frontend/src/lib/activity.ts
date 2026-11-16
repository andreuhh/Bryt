/** Pure helpers for the activity detail (no React). */

import type { ActivityStream, Divergence } from "@/lib/types";

export type SeriesRow = {
  km: number;
  elapsed: number;
  pace: number | null; // s/km, smoothed
  hr: number | null;
  cadence: number | null;
  elevation: number | null;
};

const SMOOTH_WINDOW = 25; // samples (~25-30 s): GPS pace second by second is noise

function rollingMean(values: (number | null)[], window: number): (number | null)[] {
  const half = Math.floor(window / 2);
  return values.map((_, i) => {
    let sum = 0;
    let n = 0;
    for (let j = Math.max(0, i - half); j <= Math.min(values.length - 1, i + half); j++) {
      const v = values[j];
      if (v !== null && Number.isFinite(v)) {
        sum += v;
        n++;
      }
    }
    return n ? sum / n : null;
  });
}

/** Pace is smoothed through speed (averaging s/km would overweight slow samples). */
export function buildSeries(stream: ActivityStream): SeriesRow[] {
  const speed = stream.pace_s_per_km.map((p) => (p && p > 0 ? 1000 / p : null));
  const smoothSpeed = rollingMean(speed, SMOOTH_WINDOW);
  const hr = rollingMean(stream.heart_rate, 5);
  const cadence = rollingMean(stream.cadence_spm, 9);
  // Some devices omit distance on a few records: carry the last known value forward,
  // otherwise the x axis would jump back to 0 and draw lines across the chart.
  let lastDistance = 0;
  const distance = stream.distance_m.map((d) => (lastDistance = d ?? lastDistance));
  return stream.elapsed_s.map((elapsed, i) => {
    const s = smoothSpeed[i];
    return {
      km: distance[i] / 1000,
      elapsed,
      pace: s && s >= 1 ? 1000 / s : null, // below 1 m/s = walking/standing
      hr: hr[i],
      cadence: cadence[i],
      elevation: stream.elevation_m[i],
    };
  });
}

/** Robust axis domain: ignores stop/sprint spikes (percentiles), padded a little. */
export function robustDomain(values: (number | null)[], lo = 0.02, hi = 0.98): [number, number] | undefined {
  const sorted = values.filter((v): v is number => v !== null).sort((a, b) => a - b);
  if (!sorted.length) return undefined;
  const a = sorted[Math.floor(lo * (sorted.length - 1))];
  const b = sorted[Math.ceil(hi * (sorted.length - 1))];
  const pad = (b - a) * 0.08 || 1;
  return [Math.floor(a - pad), Math.ceil(b + pad)];
}

/** Min / middle / max ticks so every small multiple shows its scale. */
export function threeTicks(domain: [number, number] | undefined): number[] | undefined {
  if (!domain) return undefined;
  const [a, b] = domain;
  return [a, Math.round((a + b) / 2), b];
}

/** Elapsed seconds → km on the chart's x axis (nearest sample). */
export function kmAt(rows: SeriesRow[], elapsed: number): number {
  let best = rows[0];
  for (const r of rows) {
    if (Math.abs(r.elapsed - elapsed) < Math.abs(best.elapsed - elapsed)) best = r;
    if (r.elapsed > elapsed) break;
  }
  return best?.km ?? 0;
}

export type Segment = {
  kind: "reference" | "final";
  label: string;
  shortLabel: string; // phones: the long labels of both windows would collide
  /** The final window is where a breakdown is detected; the reference is the "normal" run. */
  breakdown: boolean;
  from: number;
  to: number;
};

/** The two windows the deterministic divergence analysis compares. */
export function divergenceSegments(rows: SeriesRow[], d: Divergence | undefined): Segment[] {
  if (!rows.length || !d?.evaluated || !d.baseline || !d.final) return [];
  const breakdown = Boolean(d.mechanical_breakdown);
  return [
    {
      kind: "reference",
      label: "Tratto di riferimento · corsa regolare",
      shortLabel: "Riferimento",
      breakdown: false,
      from: kmAt(rows, d.baseline.start_s),
      to: kmAt(rows, d.baseline.end_s),
    },
    {
      kind: "final",
      label: breakdown ? "Tratto finale · cedimento" : "Tratto finale · nessun cedimento",
      shortLabel: breakdown ? "Finale · cedimento" : "Finale · ok",
      breakdown,
      from: kmAt(rows, d.final.start_s),
      to: kmAt(rows, d.final.end_s),
    },
  ];
}

export function signed(value: number | null | undefined, unit = "", digits = 1): string {
  if (value === null || value === undefined) return "–";
  const v = Number(value.toFixed(digits));
  return `${v > 0 ? "+" : ""}${String(v).replace(".", ",")}${unit}`;
}
