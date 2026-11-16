"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { robustDomain, type Segment, type SeriesRow, threeTicks } from "@/lib/activity";
import { pace } from "@/lib/format";

type Metric = {
  key: "pace" | "hr" | "cadence";
  title: string;
  unit: string;
  color: string;
  format: (v: number) => string;
  reversed?: boolean;
};

const METRICS: Metric[] = [
  { key: "pace", title: "Passo", unit: "/km", color: "var(--bryt-chart-pace)", format: (v) => pace(v), reversed: true },
  { key: "hr", title: "Frequenza cardiaca", unit: "bpm", color: "var(--bryt-chart-hr)", format: (v) => `${Math.round(v)}` },
  {
    key: "cadence",
    title: "Cadenza",
    unit: "spm",
    color: "var(--bryt-chart-cadence)",
    format: (v) => `${Math.round(v)}`,
  },
];

/** Plot area offsets: must match the YAxis width and the chart margins below. */
const PLOT_LEFT = 40;
const PLOT_RIGHT = 6;

const bandFill = (s: Segment) =>
  s.breakdown ? "color-mix(in srgb, var(--bryt-accent-load) 14%, transparent)" : "var(--bryt-chart-reference-soft)";

/** Labels aligned above the shaded bands, so they never sit on top of the lines. */
function SegmentStrip({ segments, maxKm }: { segments: Segment[]; maxKm: number }) {
  const km = (v: number) => v.toFixed(1).replace(".", ",");
  return (
    <div className="relative mb-1 h-10" aria-label="Tratti confrontati dall'analisi del cedimento">
      {segments.map((s) => {
        const left = maxKm ? s.from / maxKm : 0;
        const width = maxKm ? (s.to - s.from) / maxKm : 0;
        return (
          <div
            key={s.kind}
            className="absolute bottom-0"
            style={{
              left: `calc(${PLOT_LEFT}px + (100% - ${PLOT_LEFT + PLOT_RIGHT}px) * ${left})`,
              width: `calc((100% - ${PLOT_LEFT + PLOT_RIGHT}px) * ${width})`,
            }}
          >
            {/* Text may be wider than a short window: the final label grows leftwards, the
                reference label rightwards, so neither is truncated */}
            <div
              className={`absolute bottom-0 flex flex-col whitespace-nowrap pb-1 text-[11px] leading-tight ${
                s.kind === "final" ? "right-0 items-end text-right" : "left-0"
              }`}
            >
              <span className={`flex items-center gap-1.5 font-medium ${s.breakdown ? "text-fg" : "text-fg-muted"}`}>
                <span
                  aria-hidden
                  className={`h-3 w-4 shrink-0 rounded-sm ${
                    s.breakdown ? "bg-accent-load/60" : "bg-[var(--bryt-chart-reference)]"
                  }`}
                />
                <span className="sm:hidden">{s.shortLabel}</span>
                <span className="hidden sm:inline">{s.label}</span>
              </span>
              <span className="metric text-fg-subtle">
                km {km(s.from)} – {km(s.to)}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Small multiples sharing the distance axis and a synced crosshair (never two y-axes).
 * Shaded bands = the windows compared by the deterministic divergence analysis.
 */
export function TelemetryCharts({ rows, segments }: { rows: SeriesRow[]; segments: Segment[] }) {
  const visible = METRICS.filter((m) => rows.some((r) => r[m.key] !== null));
  const maxKm = rows.at(-1)?.km ?? 0;

  return (
    <div className="flex flex-col gap-1">
      {segments.length > 0 && <SegmentStrip segments={segments} maxKm={maxKm} />}
      {visible.map((m, i) => {
        const last = i === visible.length - 1;
        const domain = robustDomain(rows.map((r) => r[m.key]));
        return (
          <figure key={m.key} aria-label={`${m.title} lungo la corsa`}>
            <figcaption className="flex items-baseline justify-between px-1 text-xs">
              <span className="font-medium text-fg">{m.title}</span>
              <span className="text-fg-subtle">{m.unit}</span>
            </figcaption>
            <div className={last ? "h-36" : "h-28"}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rows} syncId="telemetry" margin={{ top: 10, right: PLOT_RIGHT, bottom: 0, left: 0 }}>
                  <CartesianGrid vertical={false} stroke="var(--bryt-chart-grid)" />
                  {segments.map((s) => (
                    <ReferenceArea
                      key={s.kind}
                      x1={s.from}
                      x2={s.to}
                      fill={bandFill(s)}
                      fillOpacity={1}
                      ifOverflow="hidden"
                    />
                  ))}
                  <XAxis
                    dataKey="km"
                    type="number"
                    domain={[0, maxKm]}
                    hide={!last}
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: "var(--bryt-fg-subtle)", fontSize: 11 }}
                    tickFormatter={(v: number) => `${Math.round(v)} km`}
                  />
                  <YAxis
                    width={PLOT_LEFT}
                    reversed={m.reversed}
                    domain={domain ?? ["auto", "auto"]}
                    ticks={threeTicks(domain)}
                    allowDataOverflow
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: "var(--bryt-fg-subtle)", fontSize: 11 }}
                    tickFormatter={m.format}
                  />
                  <Tooltip
                    cursor={{ stroke: "var(--bryt-fg-subtle)", strokeWidth: 1 }}
                    content={({ active, payload }) => {
                      const row = active && payload?.[0] ? (payload[0].payload as SeriesRow) : null;
                      const value = row?.[m.key];
                      if (!row || value === null || value === undefined) return null;
                      return (
                        <div className="metric rounded-card border border-line bg-surface px-3 py-1.5 text-xs shadow-xl">
                          <span className="text-fg">
                            {m.format(value)} {m.unit}
                          </span>
                          <span className="ml-2 text-fg-subtle">km {row.km.toFixed(2).replace(".", ",")}</span>
                        </div>
                      );
                    }}
                  />
                  <Line
                    dataKey={m.key}
                    stroke={m.color}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4, stroke: "var(--bryt-surface)", strokeWidth: 2 }}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </figure>
        );
      })}
    </div>
  );
}
