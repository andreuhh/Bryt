import { daysBetween, formatShort } from "@/lib/format";
import { PHASE_LABEL } from "@/lib/plan";
import type { TrainingPlan } from "@/lib/types";

/** Blocks as proportional segments across the whole plan, with a "today" marker. */
export function PhaseTimeline({ plan, today }: { plan: TrainingPlan; today: string }) {
  const total = daysBetween(plan.start_date, plan.end_date) + 1;
  const blocks = [...plan.blocks].sort((a, b) => a.start_date.localeCompare(b.start_date));
  const todayPct = Math.min(Math.max((daysBetween(plan.start_date, today) / total) * 100, 0), 100);
  const inPlan = today >= plan.start_date && today <= plan.end_date;

  return (
    <div className="flex flex-col gap-3">
      <div className="relative">
        <div className="flex h-10 gap-0.5 overflow-hidden rounded-card">
          {blocks.map((b) => {
            const days = daysBetween(b.start_date, b.end_date) + 1;
            const current = b.start_date <= today && today <= b.end_date;
            return (
              <a
                key={b.start_date}
                href={`#block-${b.start_date}`}
                title={`${b.name} · ${formatShort(b.start_date)} – ${formatShort(b.end_date)}`}
                style={{ width: `${(days / total) * 100}%` }}
                className={`flex min-w-0 items-center justify-center px-1 text-[11px] font-medium transition hover:brightness-125 ${
                  current ? "bg-accent-pace/20 text-fg" : "bg-elevated text-fg-muted"
                }`}
              >
                <span className="truncate">{PHASE_LABEL[b.phase]}</span>
              </a>
            );
          })}
        </div>
        {inPlan && (
          <div
            className="pointer-events-none absolute -top-1.5 bottom-[-6px] w-0.5 rounded-pill bg-fg"
            style={{ left: `${todayPct}%` }}
            aria-hidden
          />
        )}
      </div>
      <div className="flex justify-between text-xs text-fg-subtle">
        <span>{formatShort(plan.start_date)}</span>
        <span>{formatShort(plan.end_date)}</span>
      </div>
    </div>
  );
}
