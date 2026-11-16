"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { IconRefresh } from "@/components/icons";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useToast } from "@/components/ui/Toast";
import { useIntervalsSync, useUploadFit } from "@/lib/queries";
import { syncSummary } from "@/lib/dashboard";
import type { Activity } from "@/lib/types";

export function UploadCard({
  intervalsConnected,
  autoSyncing,
  onUploaded,
}: {
  intervalsConnected: boolean;
  /** The sync started automatically when the dashboard opened. */
  autoSyncing: boolean;
  onUploaded: (activity: Activity) => void;
}) {
  const toast = useToast();
  const upload = useUploadFit();
  const sync = useIntervalsSync();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const send = (file: File | undefined) => {
    if (!file) return;
    upload.mutate(file, {
      onSuccess: (result) => {
        if (result.created) onUploaded(result.activity);
        else toast("Questa corsa era già stata caricata", "neutral");
      },
      onError: (e) => toast(e.message, "error"),
    });
  };

  return (
    <Card className="flex flex-col gap-4">
      <div>
        <h2 className="font-semibold">Aggiungi una corsa</h2>
        <p className="text-sm text-fg-muted">File .fit originale, anche compresso (.gz) o lo .zip di Garmin Connect.</p>
      </div>

      <button
        type="button"
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          send(e.dataTransfer.files[0]);
        }}
        disabled={upload.isPending}
        className={`flex min-h-32 flex-col items-center justify-center gap-2 rounded-card border border-dashed px-4 py-6 text-center text-sm transition ${
          dragging ? "border-accent-pace bg-accent-pace/10" : "border-line-strong hover:bg-elevated"
        }`}
      >
        {upload.isPending ? (
          <span className="flex items-center gap-2 text-fg-muted">
            <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
            Lettura del file…
          </span>
        ) : (
          <>
            <span className="font-medium text-fg">Trascina qui il file</span>
            <span className="text-fg-subtle">oppure clicca per sceglierlo</span>
          </>
        )}
      </button>
      <input
        ref={input}
        type="file"
        accept=".fit,.gz,.zip"
        className="hidden"
        onChange={(e) => {
          send(e.target.files?.[0]);
          e.target.value = "";
        }}
      />

      <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
        <Button
          variant="secondary"
          size="sm"
          disabled={!intervalsConnected}
          loading={sync.isPending || autoSyncing}
          onClick={() =>
            sync.mutate(undefined, {
              onSuccess: (r) => toast(syncSummary(r), "success"),
              onError: (e) => toast(e.message, "error"),
            })
          }
        >
          <IconRefresh width={16} height={16} />
          Sincronizza Intervals.icu
        </Button>
        {!intervalsConnected && (
          <span className="text-xs text-fg-subtle">
            <Link href="/settings" className="underline underline-offset-4 hover:text-fg">
              Collega Intervals.icu
            </Link>{" "}
            per importare le corse dall&apos;orologio.
          </span>
        )}
      </div>
    </Card>
  );
}
