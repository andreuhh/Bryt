"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatShort } from "@/lib/format";
import { LOAD_LABEL, PHASE_LABEL, type PlanWeekView } from "@/lib/plan";

type Row = {
  key: string;
  label: string;
  planned: number;
  executed: number | null;
  week: PlanWeekView;
};

/**
 * Planned weekly volume (wide neutral reference bar) with executed km overlaid
 * (narrow pace-colored bar, centered via a second hidden category axis).
 * Deload weeks use the softer reference step; the current week gets a hairline.
 */
export function VolumeChart({ weeks, today }: { weeks: PlanWeekView[]; today: string }) {
  const data: Row[] = weeks.map((w, i) => ({
    key: w.start_date,
    label: `S${i + 1}`,
    planned: w.target_volume_km ?? 0,
    executed: w.start_date <= today ? Math.round(w.executed_km * 10) / 10 : null,
    week: w,
  }));
  const current = data.find((d) => d.week.start_date <= today && today <= d.week.end_date);

  return (
    <figure className="flex min-h-0 flex-1 flex-col gap-4" aria-label="Volume settimanale pianificato ed eseguito">
      <figcaption className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-fg-muted">
        <span className="flex items-center gap-2">
          <span className="h-3 w-4 rounded-sm bg-[var(--bryt-chart-reference)]" /> Pianificato
        </span>
        <span className="flex items-center gap-2">
          <span className="h-3 w-2 rounded-sm bg-[var(--bryt-chart-pace)]" /> Eseguito
        </span>
        <span className="flex items-center gap-2">
          <span className="h-3 w-4 rounded-sm bg-[var(--bryt-chart-reference-soft)]" /> Settimana di scarico
        </span>
        <span className="ml-auto text-fg-subtle">km / settimana</span>
      </figcaption>
      {/* Fixed height on mobile; on desktop it grows to the height of the row */}
      <div className="h-72 w-full lg:h-auto lg:min-h-72 lg:flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 22, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--bryt-chart-grid)" />
            <XAxis
              xAxisId="planned"
              dataKey="label"
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--bryt-fg-subtle)", fontSize: 11 }}
              interval="preserveStartEnd"
              minTickGap={8}
            />
            <XAxis xAxisId="executed" dataKey="label" hide />
            <YAxis
              tickLine={false}
              axisLine={false}
              width={28}
              tick={{ fill: "var(--bryt-fg-subtle)", fontSize: 11 }}
            />
            <Tooltip
              cursor={{ fill: "var(--bryt-chart-grid)" }}
              content={({ active, payload }) => {
                const row = active && payload?.[0] ? (payload[0].payload as Row) : null;
                return row ? <VolumeTooltip row={row} /> : null;
              }}
            />
            {current && (
              <ReferenceLine
                xAxisId="planned"
                x={current.label}
                stroke="var(--bryt-fg-subtle)"
                strokeWidth={1}
                label={{ value: "oggi", position: "top", fill: "var(--bryt-fg-muted)", fontSize: 11 }}
              />
            )}
            <Bar xAxisId="planned" dataKey="planned" maxBarSize={22} radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {data.map((d) => (
                <Cell
                  key={d.key}
                  fill={
                    d.week.load_type === "DELOAD"
                      ? "var(--bryt-chart-reference-soft)"
                      : "var(--bryt-chart-reference)"
                  }
                />
              ))}
            </Bar>
            <Bar
              xAxisId="executed"
              dataKey="executed"
              maxBarSize={9}
              radius={[4, 4, 0, 0]}
              fill="var(--bryt-chart-pace)"
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

function VolumeTooltip({ row }: { row: Row }) {
  const { week } = row;
  return (
    <div className="min-w-48 rounded-card border border-line bg-surface p-3 text-xs shadow-xl">
      <p className="font-medium text-fg">
        Settimana {row.label.slice(1)} · {formatShort(week.start_date)} – {formatShort(week.end_date)}
      </p>
      <p className="mt-0.5 text-fg-subtle">
        {PHASE_LABEL[week.block.phase]} · {LOAD_LABEL[week.load_type]}
      </p>
      <dl className="metric mt-2 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1">
        <dt className="text-fg-muted">Pianificato</dt>
        <dd className="text-right text-fg">{row.planned} km</dd>
        {row.executed !== null && (
          <>
            <dt className="text-fg-muted">Eseguito</dt>
            <dd className="text-right text-fg">{row.executed} km</dd>
          </>
        )}
      </dl>
    </div>
  );
}
