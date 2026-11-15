type Accent = "pace" | "load" | "nutrition" | "neutral";

const accentClass: Record<Accent, string> = {
  pace: "text-accent-pace",
  load: "text-accent-load",
  nutrition: "text-accent-nutrition",
  neutral: "text-fg",
};

type MetricProps = {
  label: string;
  value: string;
  unit?: string;
  accent?: Accent;
};

export function Metric({ label, value, unit, accent = "neutral" }: MetricProps) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs uppercase tracking-wider text-fg-subtle">{label}</span>
      <span className={`metric text-3xl font-bold ${accentClass[accent]}`}>
        {value}
        {unit && <span className="ml-1 text-base font-medium text-fg-muted">{unit}</span>}
      </span>
    </div>
  );
}
