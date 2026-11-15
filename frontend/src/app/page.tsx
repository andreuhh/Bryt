import { Wordmark } from "@/components/brand/Wordmark";
import { Card } from "@/components/ui/Card";
import { Metric } from "@/components/ui/Metric";
import { Pill } from "@/components/ui/Pill";

/** STEP 1 placeholder: design-token smoke test. Replaced by real routes in STEP 5. */
export default function Home() {
  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10 sm:px-6">
      <header className="mb-10 flex items-center justify-between">
        <Wordmark className="text-xl" />
        <div className="flex gap-2">
          <Pill active>7G</Pill>
          <Pill>30G</Pill>
          <Pill>90G</Pill>
        </div>
      </header>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card className="md:col-span-2">
          <h1 className="text-3xl font-bold">Design token check</h1>
          <p className="mt-2 text-fg-muted">
            Canvas, surface, elevated e accenti semantici risolti da CSS Custom Properties.
          </p>
          <div className="mt-6 grid grid-cols-3 gap-3">
            <Card variant="card" className="bg-elevated">
              <Metric label="Passo soglia" value="3:52" unit="/km" accent="pace" />
            </Card>
            <Card variant="card" className="bg-elevated">
              <Metric label="Carico mecc." value="412" unit="AU" accent="load" />
            </Card>
            <Card variant="card" className="bg-elevated">
              <Metric label="Carbo" value="8.5" unit="g/kg" accent="nutrition" />
            </Card>
          </div>
        </Card>
        <Card className="flex flex-col justify-between">
          <span className="text-xs uppercase tracking-wider text-fg-subtle">Status</span>
          <span className="metric text-5xl font-bold text-accent-pace">STEP 1</span>
          <span className="text-sm text-fg-muted">Scaffolding completato</span>
        </Card>
      </section>
    </main>
  );
}
