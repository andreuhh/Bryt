import { WorkoutRow } from "@/components/plan/WorkoutRow";
import { Badge } from "@/components/ui/Badge";
import { formatShort } from "@/lib/format";
import { LOAD_LABEL, PHASE_LABEL, type PlanWeekView } from "@/lib/plan";
import type { Workout } from "@/lib/types";

/** Every week of the plan grouped by block; the current week starts open. Doubles as the
 * table view of the volume chart. */
export function WeekList({
  weeks,
  today,
  onOpen,
}: {
  weeks: PlanWeekView[];
  today: string;
  onOpen: (w: Workout) => void;
}) {
  const blocks = weeks.reduce<{ start: string; weeks: PlanWeekView[] }[]>((acc, w) => {
    const last = acc.at(-1);
    if (last && last.start === w.block.start_date) last.weeks.push(w);
    else acc.push({ start: w.block.start_date, weeks: [w] });
    return acc;
  }, []);

  return (
    <div className="flex flex-col gap-8">
      {blocks.map(({ start, weeks: blockWeeks }) => {
        const block = blockWeeks[0].block;
        return (
          <section key={start} id={`block-${start}`} className="flex scroll-mt-24 flex-col gap-3">
            <header className="flex flex-col gap-1 px-1">
              <p className="text-xs font-medium uppercase tracking-wider text-fg-subtle">
                {PHASE_LABEL[block.phase]} · {formatShort(block.start_date)} – {formatShort(block.end_date)}
              </p>
              <h3 className="text-lg font-semibold">{block.name}</h3>
              <p className="max-w-3xl text-sm text-fg-muted">{block.objective}</p>
            </header>
            <div className="flex flex-col gap-2">
              {blockWeeks.map((week) => {
                const index = weeks.indexOf(week) + 1;
                const current = week.start_date <= today && today <= week.end_date;
                return (
                  <details
                    key={week.start_date}
                    open={current}
                    className="group rounded-container border border-line bg-surface"
                  >
                    <summary className="flex cursor-pointer list-none items-center gap-3 px-5 py-4 [&::-webkit-details-marker]:hidden">
                      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                        <span className="flex flex-wrap items-center gap-2 text-sm font-medium">
                          Settimana {index}
                          <span className="font-normal text-fg-subtle">
                            {formatShort(week.start_date)} – {formatShort(week.end_date)}
                          </span>
                          {current && <Badge tone="pace">Questa settimana</Badge>}
                          {week.load_type !== "LOAD" && <Badge>{LOAD_LABEL[week.load_type]}</Badge>}
                        </span>
                        {week.focus && <span className="line-clamp-1 text-xs text-fg-muted">{week.focus}</span>}
                      </span>
                      <span className="metric shrink-0 text-right">
                        <span className="block text-base font-semibold">{week.target_volume_km ?? "–"} km</span>
                        {week.executed_km > 0 && (
                          <span className="block text-xs text-fg-muted">
                            {week.executed_km.toFixed(1).replace(".", ",")} km fatti
                          </span>
                        )}
                      </span>
                    </summary>
                    <div className="flex flex-col border-t border-line px-2 py-2">
                      {week.workouts.length ? (
                        week.workouts.map((w) => <WorkoutRow key={w.id} workout={w} today={today} onOpen={onOpen} />)
                      ) : (
                        <p className="px-3 py-2 text-sm text-fg-subtle">Nessuna sessione.</p>
                      )}
                    </div>
                  </details>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
