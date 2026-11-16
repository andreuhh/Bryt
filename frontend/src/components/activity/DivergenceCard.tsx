import { IconAlert, IconCheck } from "@/components/icons";
import { Card } from "@/components/ui/Card";
import { signed } from "@/lib/activity";
import { pace } from "@/lib/format";
import type { Divergence } from "@/lib/types";

/** Deterministic Cadence-vs-HR divergence: what was compared and why it fired (or not). */
export function DivergenceCard({ divergence }: { divergence: Divergence }) {
  if (!divergence.evaluated)
    return (
      <Card>
        <h2 className="font-semibold">Divergenza cadenza / FC</h2>
        <p className="mt-2 text-sm text-fg-muted">Non valutata: {divergence.reason ?? "dati insufficienti"}.</p>
      </Card>
    );

  const b = divergence.baseline!;
  const f = divergence.final!;
  const breakdown = divergence.mechanical_breakdown;
  const rows = [
    { label: "Cadenza", a: b.cadence_spm, z: f.cadence_spm, fmt: (v: number) => `${Math.round(v)} spm`, flag: divergence.cadence_drop_detected },
    {
      label: "Lunghezza del passo",
      a: b.stride_length_m,
      z: f.stride_length_m,
      fmt: (v: number) => `${v.toFixed(2).replace(".", ",")} m`,
      flag: divergence.stride_length_drop_detected,
    },
    { label: "Tempo di contatto", a: b.ground_contact_ms, z: f.ground_contact_ms, fmt: (v: number) => `${Math.round(v)} ms`, flag: divergence.ground_contact_rise_detected },
    { label: "Frequenza cardiaca", a: b.heart_rate, z: f.heart_rate, fmt: (v: number) => `${Math.round(v)} bpm`, flag: false },
    { label: "Passo", a: b.pace_s_per_km, z: f.pace_s_per_km, fmt: (v: number) => `${pace(v)}/km`, flag: false },
  ].filter((r) => r.a !== null && r.a !== undefined && r.z !== null && r.z !== undefined);

  return (
    <Card className={breakdown ? "border-accent-load/40" : undefined}>
      <div className="flex items-start gap-3">
        {breakdown ? (
          <IconAlert className="mt-0.5 shrink-0 text-accent-load" />
        ) : (
          <IconCheck className="mt-0.5 shrink-0 text-accent-pace" />
        )}
        <div>
          <h2 className="font-semibold">{breakdown ? "Cedimento meccanico muscolare" : "Nessun cedimento meccanico"}</h2>
          <p className="mt-1 text-sm text-fg-muted">
            {breakdown
              ? "Nel finale le gambe hanno perso efficacia mentre la frequenza cardiaca restava stabile: è fatica muscolare, non cardiovascolare."
              : divergence.hr_stable === false
                ? `La FC è cambiata di ${signed(divergence.hr_change_pct, "%")} nel finale: se sale a passo costante o più lento è un segnale cardiovascolare, non meccanico.`
                : "Cadenza, lunghezza del passo e appoggio sono rimasti stabili fino alla fine."}
          </p>
        </div>
      </div>

      <table className="metric mt-5 w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-fg-subtle">
            <th className="pb-2 font-normal">Finale vs riferimento</th>
            <th className="pb-2 text-right font-normal">Riferimento</th>
            <th className="pb-2 text-right font-normal">Finale</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-t border-line">
              <td className="py-2 text-fg-muted">
                {r.label}
                {r.flag && <span className="ml-2 text-xs text-accent-load">oltre soglia</span>}
              </td>
              <td className="py-2 text-right text-fg-muted">{r.fmt(r.a!)}</td>
              <td className="py-2 text-right text-fg">{r.fmt(r.z!)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-xs text-fg-subtle">
        Soglie: cadenza −4 spm, passo −8%, contatto al suolo +4%, con FC stabile (±3%).
      </p>
    </Card>
  );
}
