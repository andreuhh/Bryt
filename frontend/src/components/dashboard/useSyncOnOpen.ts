"use client";

import { useEffect, useRef } from "react";

import { useToast } from "@/components/ui/Toast";
import { syncCounts } from "@/lib/dashboard";
import { useIntervalsSync } from "@/lib/queries";
import type { Profile } from "@/lib/types";

/** Below this age the backend poll (every 15') or a previous visit already looked. */
const FRESH_MS = 10 * 60 * 1000;

/**
 * Opening the dashboard right after a run shows it without pressing anything: one Intervals.icu
 * sync per visit when the last one is older than a few minutes. New runs are analyzed by the
 * backend right away; `onImported` lets the page follow that analysis.
 */
export function useSyncOnOpen(profile: Profile | undefined, onImported: (activityId: string) => void) {
  const sync = useIntervalsSync();
  const toast = useToast();
  const started = useRef(false);

  useEffect(() => {
    if (started.current || !profile?.intervals_connected) return;
    const last = profile.intervals_synced_at ? Date.parse(profile.intervals_synced_at) : 0;
    if (Date.now() - last < FRESH_MS) return;
    started.current = true;
    sync.mutate(undefined, {
      onSuccess: (result) => {
        const imported = result.items.filter((i) => i.status === "IMPORTED" && i.activity_id);
        if (!imported.length) return;
        const { imported: n } = syncCounts(result);
        toast(n === 1 ? "Nuova corsa da Intervals.icu: la stiamo analizzando" : `${n} nuove corse da Intervals.icu`, "success");
        onImported(imported[imported.length - 1].activity_id!);
      },
      // Silent: the manual button and the backend poll remain; a failure here is not actionable
    });
  }, [profile, sync, toast, onImported]);

  return sync.isPending;
}
