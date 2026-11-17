"use client";

import { type ReactNode, useEffect, useState } from "react";

import { Wordmark } from "@/components/brand/Wordmark";
import { IconCheck, IconStar } from "@/components/icons";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DurationInput, Field, MultiPills, NumberInput, TextArea, TextInput } from "@/components/ui/Field";
import { Metric } from "@/components/ui/Metric";
import { Modal } from "@/components/ui/Modal";
import { Pill } from "@/components/ui/Pill";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { useToast } from "@/components/ui/Toast";

const GROUPS: { title: string; prefixes: string[]; note: string }[] = [
  { title: "Superfici", prefixes: ["--bryt-canvas", "--bryt-surface", "--bryt-elevated"], note: "canvas = sfondo app · surface = card · elevated = pill, bottoni, input" },
  { title: "Bordi", prefixes: ["--bryt-border"], note: "Bordi 1px: line per separare, strong per input e stati attivi" },
  { title: "Testo", prefixes: ["--bryt-fg"], note: "fg = testo principale · muted = secondario · subtle = etichette e note" },
  { title: "Accenti semantici", prefixes: ["--bryt-accent", "--bryt-on-accent"], note: "Legati al dominio: mai decorativi" },
  { title: "Grafici", prefixes: ["--bryt-chart"], note: "Unici colori ammessi nei grafici Recharts" },
];

const ACCENTS: { token: string; className: string; label: string; use: string; avoid: string }[] = [
  { token: "pace", className: "bg-accent-pace", label: "Pace", use: "Target centrati, efficienza aerobica, sessioni chiave, completato", avoid: "Stati generici di successo fuori dal dominio corsa" },
  { token: "load", className: "bg-accent-load", label: "Load", use: "Stress meccanico, quadricipiti, alert reali, errori", avoid: "Stati informativi (es. sessione modificata): usare neutral" },
  { token: "nutrition", className: "bg-accent-nutrition", label: "Nutrition", use: "Carboidrati, proteine, recupero", avoid: "Link o accenti decorativi" },
];

function readTokenNames(): string[] {
  const names = new Set<string>();
  const visit = (rules: CSSRuleList) => {
    for (const rule of Array.from(rules)) {
      if (rule instanceof CSSStyleRule && rule.selectorText.startsWith(":root")) {
        for (const prop of Array.from(rule.style)) if (prop.startsWith("--bryt-")) names.add(prop);
      }
      if ("cssRules" in rule) visit((rule as CSSGroupingRule).cssRules);
    }
  };
  for (const sheet of Array.from(document.styleSheets)) {
    try {
      visit(sheet.cssRules);
    } catch {
      /* cross-origin stylesheet (fonts): not ours */
    }
  }
  return [...names];
}

function useTokens() {
  const [tokens, setTokens] = useState<{ name: string; value: string }[]>([]);
  useEffect(() => {
    const read = () => {
      const style = getComputedStyle(document.documentElement);
      setTokens(readTokenNames().map((name) => ({ name, value: style.getPropertyValue(name).trim() })));
    };
    read();
    const observer = new MutationObserver(read);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  return tokens;
}

function Section({ id, title, description, children }: { id: string; title: string; description?: string; children: ReactNode }) {
  return (
    <section id={id} className="flex scroll-mt-6 flex-col gap-4">
      <div>
        <h2 className="text-2xl font-semibold">{title}</h2>
        {description && <p className="mt-1 max-w-2xl text-sm text-fg-muted">{description}</p>}
      </div>
      {children}
    </section>
  );
}

function Label({ children }: { children: ReactNode }) {
  return <p className="text-xs font-medium uppercase tracking-wider text-fg-subtle">{children}</p>;
}

function Swatch({ name, value }: { name: string; value: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="size-12 shrink-0 rounded-card border border-line-strong" style={{ background: `var(${name})` }} />
      <div className="min-w-0">
        <p className="truncate font-mono text-xs text-fg">{name}</p>
        <p className="metric truncate text-xs text-fg-muted">{value}</p>
      </div>
    </div>
  );
}

const NAV = [
  ["colori", "Colori"],
  ["accenti", "Accenti"],
  ["tipografia", "Tipografia"],
  ["forme", "Forme"],
  ["componenti", "Componenti"],
  ["form", "Form"],
  ["stati", "Stati"],
  ["grafici", "Grafici"],
] as const;

export function DesignSystemView() {
  const tokens = useTokens();
  const toast = useToast();
  const [modalOpen, setModalOpen] = useState(false);
  const [segment, setSegment] = useState<"7" | "30" | "90">("30");
  const [days, setDays] = useState<string[]>(["TUE", "THU"]);
  const [duration, setDuration] = useState({ h: "3", m: "05", s: "12" });
  const colors = tokens.filter((t) => !t.name.startsWith("--bryt-radius"));
  const radii = tokens.filter((t) => t.name.startsWith("--bryt-radius"));

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-14 px-4 py-8 sm:px-8">
      <header className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-4">
          <Wordmark />
          <ThemeToggle />
        </div>
        <div>
          <h1 className="text-4xl font-bold">Design system</h1>
          <p className="mt-2 max-w-2xl text-sm text-fg-muted">
            Token e componenti reali dell&apos;app, letti da <code className="font-mono">globals.css</code> e{" "}
            <code className="font-mono">components/ui</code>. Pagina solo di sviluppo: non esiste nel build di produzione.
          </p>
        </div>
        <nav className="flex flex-wrap gap-2">
          {NAV.map(([id, label]) => (
            <a key={id} href={`#${id}`} className="rounded-pill bg-elevated px-3 py-1.5 text-xs text-fg-muted hover:bg-elevated-hover hover:text-fg">
              {label}
            </a>
          ))}
        </nav>
      </header>

      <Section id="colori" title="Colori" description="Ogni colore dell'app è un token --bryt-*. Vietato usare hex o rgba nei componenti. Cambia tema in alto per vedere i valori light.">
        {GROUPS.map((g) => {
          const items = colors.filter((t) => g.prefixes.some((p) => t.name.startsWith(p)));
          return (
            <Card key={g.title} className="flex flex-col gap-4">
              <div>
                <h3 className="font-semibold">{g.title}</h3>
                <p className="text-sm text-fg-muted">{g.note}</p>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {items.map((t) => (
                  <Swatch key={t.name} {...t} />
                ))}
              </div>
            </Card>
          );
        })}
      </Section>

      <Section id="accenti" title="Accenti semantici" description="Ogni accento appartiene a un dominio. Uno stato senza significato di dominio usa i toni neutri.">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {ACCENTS.map((a) => (
            <Card key={a.token} variant="card" className="flex flex-col gap-3 border border-line">
              <span className={`h-2 w-12 rounded-pill ${a.className}`} />
              <p className="font-semibold">{a.label}</p>
              <div className="text-sm">
                <p className="text-fg-muted">
                  <span className="text-fg">Sì:</span> {a.use}
                </p>
                <p className="mt-1 text-fg-muted">
                  <span className="text-fg">No:</span> {a.avoid}
                </p>
              </div>
            </Card>
          ))}
        </div>
      </Section>

      <Section id="tipografia" title="Tipografia" description="Plus Jakarta Sans (font-display) per titoli e numeri, Inter (font-sans) per il testo. Ogni dato telemetrico usa la utility metric (cifre tabulari).">
        <Card className="flex flex-col gap-6">
          <div className="flex flex-col gap-3">
            <Label>Titoli · font-display</Label>
            <p className="font-display text-4xl font-bold">Facile 40&apos; Z1-Z2</p>
            <h2 className="text-2xl font-semibold">Analisi degli agent</h2>
            <h3 className="font-semibold">Carico rispetto alla tua storia</h3>
          </div>
          <div className="flex flex-col gap-2">
            <Label>Testo · font-sans</Label>
            <p className="text-sm">Testo principale (text-sm, fg): la corsa è stata eseguita come da piano.</p>
            <p className="text-sm text-fg-muted">Testo secondario (fg-muted): dettagli e spiegazioni.</p>
            <p className="text-xs uppercase tracking-wider text-fg-subtle">Etichetta (xs, uppercase, fg-subtle)</p>
          </div>
          <div className="flex flex-col gap-2">
            <Label>Numeri · metric</Label>
            <p className="metric text-4xl font-bold">
              4:36<span className="ml-1 text-base font-medium text-fg-muted">/km</span>
            </p>
            <p className="metric text-sm text-fg-muted">111 111 · 888 888 (larghezza costante)</p>
          </div>
          <div className="flex flex-col gap-2">
            <Label>Wordmark</Label>
            <Wordmark />
          </div>
        </Card>
      </Section>

      <Section id="forme" title="Forme e superfici" description="Bento grid: contenitori rounded-container, card interne rounded-card, azioni rounded-pill.">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {radii.map((r) => (
            <div key={r.name} className="flex flex-col gap-2">
              <div className="h-24 border border-line-strong bg-surface" style={{ borderRadius: `var(${r.name})` }} />
              <p className="font-mono text-xs">{r.name}</p>
              <p className="metric text-xs text-fg-muted">{r.value}</p>
            </div>
          ))}
        </div>
        <div className="rounded-container bg-canvas p-4 ring-1 ring-line">
          <Label>canvas</Label>
          <div className="mt-3 rounded-container bg-surface p-4">
            <Label>surface (Card)</Label>
            <div className="mt-3 rounded-card bg-elevated p-4">
              <Label>elevated</Label>
            </div>
          </div>
        </div>
      </Section>

      <Section id="componenti" title="Componenti" description="components/ui: primitive custom, nessuna libreria esterna.">
        <Card className="flex flex-col gap-6">
          <div className="flex flex-col gap-3">
            <Label>Button · variant × size</Label>
            {(["md", "sm"] as const).map((size) => (
              <div key={size} className="flex flex-wrap items-center gap-3">
                <Button size={size}>Primary</Button>
                <Button size={size} variant="secondary">
                  Secondary
                </Button>
                <Button size={size} variant="ghost">
                  Ghost
                </Button>
                <Button size={size} variant="danger">
                  Danger
                </Button>
              </div>
            ))}
            <div className="flex flex-wrap items-center gap-3">
              <Button loading>Loading</Button>
              <Button disabled>Disabled</Button>
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <Label>Badge · tone</Label>
            <div className="flex flex-wrap gap-2">
              <Badge>neutral</Badge>
              <Badge tone="outline">outline</Badge>
              <Badge tone="pace">pace</Badge>
              <Badge tone="load">load</Badge>
              <Badge tone="nutrition">nutrition</Badge>
            </div>
            <Label>Badge · usi reali</Label>
            <div className="flex flex-wrap gap-2">
              <Badge tone="pace">
                <IconStar width={12} height={12} />
                Chiave
              </Badge>
              <Badge tone="pace">
                <IconCheck width={12} height={12} />
                Fatto
              </Badge>
              <Badge>Modificata</Badge>
              <Badge tone="outline">Provvisoria</Badge>
              <Badge tone="outline">Analisi rapida</Badge>
              <Badge tone="load">Con cautela</Badge>
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <Label>Pill · SegmentedControl</Label>
            <div className="flex flex-wrap gap-2">
              <Pill active>Attiva</Pill>
              <Pill>Inattiva</Pill>
            </div>
            <SegmentedControl
              label="Periodo"
              value={segment}
              onChange={setSegment}
              options={[
                { value: "7", label: "7G" },
                { value: "30", label: "30G" },
                { value: "90", label: "90G" },
              ]}
            />
          </div>

          <div className="flex flex-col gap-3">
            <Label>Metric · accent</Label>
            <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
              <Metric label="Distanza" value="12,4" unit="km" />
              <Metric label="Passo" value="4:52" unit="/km" accent="pace" />
              <Metric label="Carico" value="74" unit="/100" accent="load" />
              <Metric label="Carboidrati" value="420" unit="g" accent="nutrition" />
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <Label>Card · variant</Label>
            <div className="grid grid-cols-1 gap-4 rounded-container bg-canvas p-4 sm:grid-cols-2">
              <Card>container (default): p-6, rounded-container</Card>
              <Card variant="card">card: p-4, rounded-card</Card>
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <Label>Modal · Toast</Label>
            <div className="flex flex-wrap gap-3">
              <Button variant="secondary" onClick={() => setModalOpen(true)}>
                Apri modale
              </Button>
              <Button variant="secondary" onClick={() => toast("Messaggio neutro")}>
                Toast neutral
              </Button>
              <Button variant="secondary" onClick={() => toast("Salvato", "success")}>
                Toast success
              </Button>
              <Button variant="secondary" onClick={() => toast("Non riuscito", "error")}>
                Toast error
              </Button>
            </div>
          </div>
        </Card>
      </Section>

      <Section id="form" title="Form" description="Field con etichetta, aiuto ed errore; input su superficie elevated.">
        <Card className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <Field label="Nome" hint="Testo di aiuto (fg-subtle)" required>
            <TextInput placeholder="Andrea" />
          </Field>
          <Field label="Volume settimanale" error="Inserisci un valore tra 0 e 250">
            <NumberInput invalid defaultValue={300} />
          </Field>
          <Field label="Tempo obiettivo">
            <DurationInput label="Tempo obiettivo" value={duration} onChange={setDuration} />
          </Field>
          <Field label="Giorni disponibili">
            <MultiPills
              label="Giorni disponibili"
              value={days}
              onChange={setDays}
              options={[
                { value: "MON", label: "Lun" },
                { value: "TUE", label: "Mar" },
                { value: "THU", label: "Gio" },
                { value: "SAT", label: "Sab" },
              ]}
            />
          </Field>
          <Field label="Note per il coach">
            <TextArea rows={3} placeholder="Infortuni, preferenze…" />
          </Field>
        </Card>
      </Section>

      <Section id="stati" title="Stati" description="Caricamento, vuoto ed errore (quest'ultimo sempre con Riprova).">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="flex flex-col gap-2">
            <Label>Skeleton</Label>
            <Skeleton className="h-32" />
          </div>
          <div className="flex flex-col gap-2">
            <Label>EmptyState</Label>
            <EmptyState title="Nessun piano" description="Completa l'onboarding per generarlo." action={<Button size="sm">Inizia</Button>} />
          </div>
          <div className="flex flex-col gap-2">
            <Label>ErrorState</Label>
            <ErrorState message="Backend non raggiungibile." onRetry={() => toast("Riprova")} />
          </div>
        </div>
      </Section>

      <Section id="grafici" title="Grafici" description="Wrapper Recharts in components/charts. Colori solo dai token --bryt-chart-* (vedi Colori).">
        <Card className="text-sm">
          <ul className="flex list-disc flex-col gap-2 pl-5 text-fg-muted">
            <li>Barre al massimo 24 px, estremità arrotondate 4 px.</li>
            <li>Griglia solo orizzontale e sottile (--bryt-chart-grid).</li>
            <li>Tooltip flottante custom; legenda sempre presente con 2 o più serie.</li>
            <li>Testi nei colori del testo, mai nel colore della serie.</li>
            <li>Mai due assi Y: passo, FC e cadenza sono grafici impilati con cursore sincronizzato.</li>
            <li>Asse del passo invertito; dominio robusto sui percentili 2-98.</li>
          </ul>
        </Card>
      </Section>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Titolo della modale">
        <p className="text-sm text-fg-muted">Dialog nativo: focus trap, Esc e sfondo. Su mobile diventa un bottom sheet.</p>
        <div className="mt-5 flex justify-end gap-3">
          <Button variant="ghost" onClick={() => setModalOpen(false)}>
            Annulla
          </Button>
          <Button onClick={() => setModalOpen(false)}>Conferma</Button>
        </div>
      </Modal>
    </div>
  );
}
