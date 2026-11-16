"use client";

import { type FormEvent, useState } from "react";

import { SignOutButton } from "@/components/auth/SignOutButton";
import Link from "next/link";

import { IconCheck, IconRefresh } from "@/components/icons";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api";
import { syncCounts } from "@/lib/dashboard";
import { RUN_SURFACE_HINT, RUN_SURFACE_OPTIONS } from "@/lib/onboarding";
import type { Surface, SyncResult } from "@/lib/types";
import {
  BACKFILL_WEEKS,
  useUpdateProfile,
  useIntervalsBackfill,
  useIntervalsSync,
  useMe,
  useProfile,
} from "@/lib/queries";

const ATHLETE_ID = /^i\d+$/;

function connectErrorMessage(error: Error): string {
  if (error instanceof ApiError && error.status === 422)
    return "Intervals.icu non accetta queste credenziali: controlla Athlete ID e API Key.";
  if (error instanceof ApiError && error.status === 502)
    return "Intervals.icu non risponde in questo momento. Riprova tra poco.";
  return error.message;
}

export function SettingsView() {
  const me = useMe();
  const profile = useProfile();

  if (profile.isPending || me.isPending) return <Skeleton className="h-96" />;
  if (profile.isError) return <ErrorState message={profile.error.message} onRetry={() => profile.refetch()} />;

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
      <h1 className="text-3xl font-bold">Impostazioni</h1>
      <IntervalsCard athleteId={profile.data.intervals_athlete_id} connected={profile.data.intervals_connected} />
      <SurfaceCard value={profile.data.default_run_surface} />
      <Card className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wider text-fg-subtle">Account</p>
          <p className="truncate text-sm text-fg">{me.data?.email}</p>
        </div>
        <SignOutButton className="text-sm" />
      </Card>
    </div>
  );
}

function SurfaceCard({ value }: { value: Surface | null }) {
  const toast = useToast();
  const update = useUpdateProfile();
  const current = RUN_SURFACE_OPTIONS.find((o) => o.value === value)?.value ?? "";
  return (
    <Card className="flex flex-col gap-4">
      <div>
        <h2 className="font-semibold">Superficie abituale</h2>
        <p className="text-sm text-fg-muted">
          Quando scegli “Corsa” sull&apos;orologio, di solito corri su… Vale anche per le corse già importate.
        </p>
      </div>
      <SegmentedControl
        label="Superficie abituale"
        value={current}
        options={RUN_SURFACE_OPTIONS}
        onChange={(default_run_surface) =>
          default_run_surface &&
          update.mutate(
            { default_run_surface },
            {
              onSuccess: () => toast("Superficie abituale aggiornata", "success"),
              onError: (e) => toast(e.message, "error"),
            },
          )
        }
      />
      <p className="text-xs text-fg-subtle">{RUN_SURFACE_HINT}</p>
    </Card>
  );
}

function IntervalsCard({ athleteId, connected }: { athleteId: string | null; connected: boolean }) {
  const toast = useToast();
  const connect = useUpdateProfile();
  const sync = useIntervalsSync();
  const backfill = useIntervalsBackfill();
  const [editing, setEditing] = useState(!connected);
  const [id, setId] = useState(athleteId ?? "");
  const [key, setKey] = useState("");
  const idInvalid = id.trim() !== "" && !ATHLETE_ID.test(id.trim());

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (idInvalid || !id.trim() || !key.trim()) return;
    connect.mutate(
      { intervals_athlete_id: id.trim(), intervals_api_key: key.trim() },
      {
        onSuccess: () => {
          setKey("");
          setEditing(false);
          toast("Intervals.icu collegato", "success");
        },
      },
    );
  };

  return (
    <Card className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold">Intervals.icu</h2>
          <p className="text-sm text-fg-muted">Importa le corse dal tuo orologio con il file originale.</p>
        </div>
        {connected ? <Badge tone="pace">Collegato · {athleteId}</Badge> : <Badge>Non collegato</Badge>}
      </div>

      {connected && !editing && (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="secondary"
            size="sm"
            loading={sync.isPending}
            disabled={backfill.isPending}
            onClick={() => (backfill.reset(), sync.mutate())}
          >
            <IconRefresh width={16} height={16} />
            Sincronizza ora
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
            Cambia credenziali
          </Button>
        </div>
      )}
      {sync.isError && <ErrorState message={sync.error.message} />}
      {sync.data && <SyncOutcome result={sync.data} analyzed />}

      {connected && !editing && (
        <div className="flex flex-col gap-3 border-t border-line pt-5">
          <div>
            <h3 className="text-sm font-medium">Importa lo storico</h3>
            <p className="text-sm text-fg-muted">
              Porta in BRYT le corse delle ultime {BACKFILL_WEEKS} settimane, senza analizzarle: servono a calcolare
              il tuo riferimento (volume, passo, cadenza). Nessun costo. Le corse nuove verranno analizzate come sempre.
            </p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            className="self-start"
            loading={backfill.isPending}
            disabled={sync.isPending}
            onClick={() => (sync.reset(), backfill.mutate())}
          >
            Importa le ultime {BACKFILL_WEEKS} settimane
          </Button>
          {backfill.isError && <ErrorState message={backfill.error.message} />}
          {backfill.data && <SyncOutcome result={backfill.data} analyzed={false} />}
        </div>
      )}

      {editing && (
        <form onSubmit={submit} className="flex flex-col gap-5">
          <ol className="flex list-decimal flex-col gap-1 pl-5 text-sm text-fg-muted">
            <li>
              Collega l&apos;orologio <span className="text-fg">direttamente</span> a Intervals.icu (Settings →
              Connections): le corse che arrivano da Strava non hanno il file originale e non si possono importare.
            </li>
            <li>
              L&apos;<span className="text-fg">Athlete ID</span> (es. i12345) è nell&apos;indirizzo della pagina del
              tuo profilo.
            </li>
            <li>
              L&apos;<span className="text-fg">API Key</span> è in Settings → Developer Settings.
            </li>
          </ol>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Athlete ID" required error={idInvalid ? "Ha la forma i12345" : undefined}>
              <TextInput
                value={id}
                invalid={idInvalid}
                placeholder="i12345"
                autoComplete="off"
                onChange={(e) => setId(e.target.value)}
              />
            </Field>
            <Field label="API Key" required hint="Verificata con Intervals.icu e salvata cifrata.">
              <TextInput
                type="password"
                value={key}
                autoComplete="off"
                onChange={(e) => setKey(e.target.value)}
              />
            </Field>
          </div>
          {connect.isError && <ErrorState message={connectErrorMessage(connect.error)} />}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" loading={connect.isPending} disabled={!id.trim() || !key.trim() || idInvalid}>
              {connected ? "Aggiorna" : "Collega"}
            </Button>
            {connected && (
              <Button variant="ghost" onClick={() => (setEditing(false), setKey(""), connect.reset())}>
                Annulla
              </Button>
            )}
          </div>
        </form>
      )}
    </Card>
  );
}

/** Stays visible after the import (a toast is easy to miss on a long-running action). */
function SyncOutcome({ result, analyzed }: { result: SyncResult; analyzed: boolean }) {
  const c = syncCounts(result);
  const parts = [
    c.imported && `${c.imported} ${c.imported === 1 ? "corsa importata" : "corse importate"}`,
    c.present && `${c.present} già presenti`,
    c.noFile && `${c.noFile} senza file (es. da Strava)`,
    c.failed && `${c.failed} non riuscite`,
  ].filter(Boolean);
  const next = !c.imported
    ? null
    : analyzed
      ? "Il coach le sta analizzando: trovi il report nella dashboard tra qualche minuto."
      : "Non vengono analizzate: servono a calcolare il tuo riferimento delle ultime settimane.";
  return (
    <div role="status" className="flex items-start gap-3 rounded-card border border-line bg-elevated p-4 text-sm">
      <IconCheck className="mt-0.5 shrink-0 text-accent-pace" />
      <div className="flex flex-col gap-1">
        <p className="font-medium text-fg">{c.imported ? "Import completato" : "Nessuna nuova corsa"}</p>
        <p className="text-fg-muted">
          {parts.length ? `${parts.join(" · ")}.` : "Su Intervals.icu non ci sono corse in questo periodo."}
          {next && ` ${next}`}
        </p>
        {c.imported > 0 && (
          <Link href="/dashboard" className="self-start text-fg-muted underline underline-offset-4 hover:text-fg">
            Vai alla dashboard
          </Link>
        )}
      </div>
    </div>
  );
}
