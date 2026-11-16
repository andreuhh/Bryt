"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { ContextTagsModal } from "@/components/dashboard/ContextTagsModal";
import { LatestAnalysis } from "@/components/dashboard/LatestAnalysis";
import { NextKeyTile, WeekVolumeTile } from "@/components/dashboard/StatTiles";
import { TodayCard } from "@/components/dashboard/TodayCard";
import { UploadCard } from "@/components/dashboard/UploadCard";
import { WeekStrip } from "@/components/dashboard/WeekStrip";
import { WorkoutModal } from "@/components/plan/WorkoutModal";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { ApiError } from "@/lib/api";
import { activityDay } from "@/lib/dashboard";
import { addDays, mondayOf } from "@/lib/format";
import { useToday } from "@/lib/hooks";
import { planWeeks } from "@/lib/plan";
import {
  useActivePlan,
  useActivities,
  useActivityReport,
  useMe,
  useProfile,
  useProposals,
  useWorkouts,
} from "@/lib/queries";
import type { Activity, Workout } from "@/lib/types";

export function DashboardView() {
  const today = useToday();
  const monday = today ? mondayOf(today) : undefined;
  const sunday = monday ? addDays(monday, 6) : undefined;

  const me = useMe();
  const profile = useProfile();
  const plan = useActivePlan();
  const hasPlan = plan.isSuccess && today !== null;
  const week = useWorkouts({ from: monday, to: sunday }, hasPlan);
  const keySessions = useWorkouts({ keyOnly: true }, hasPlan);
  const weekActivities = useActivities({ from: monday, to: sunday }, today !== null);
  const recent = useActivities({ limit: 5 });
  const proposals = useProposals(hasPlan);

  const [selected, setSelected] = useState<Workout | null>(null);
  const [tagging, setTagging] = useState<Activity | null>(null);
  const [watching, setWatching] = useState<string | null>(null);

  const latest = recent.data?.[0];
  const latestReport = useActivityReport(latest?.id ?? null, watching === latest?.id);
  const readiness =
    latest && today && addDays(activityDay(latest), 2) >= today
      ? (latestReport.data?.nutrition_recovery?.output?.recovery_protocol.readiness_next_session ?? null)
      : null;

  const plannedKm = useMemo(() => {
    if (!plan.data || !monday) return null;
    return planWeeks(plan.data, [], []).find((w) => w.start_date === monday)?.target_volume_km ?? null;
  }, [plan.data, monday]);
  const executedKm = (weekActivities.data ?? []).reduce((sum, a) => sum + a.distance_m / 1000, 0);

  if (today === null || plan.isPending) return <DashboardSkeleton />;

  const todayWorkouts = (week.data ?? []).filter((w) => w.scheduled_date === today);
  const nextSession = (week.data ?? []).find((w) => w.scheduled_date > today && w.workout_type !== "REST");
  const nextKey = (keySessions.data ?? []).find((w) => w.scheduled_date >= today);
  const firstName = me.data?.display_name?.split(" ")[0];

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-3xl font-bold sm:text-4xl">{firstName ? `Ciao, ${firstName}` : "Ciao"}</h1>
        {plan.data && (
          <p className="text-sm text-fg-muted">
            {plan.data.name} ·{" "}
            <Link href="/plan" className="underline decoration-line-strong underline-offset-4 hover:decoration-fg">
              apri il piano
            </Link>
          </p>
        )}
      </header>

      {(proposals.data?.length ?? 0) > 0 && (
        <Link
          href="/plan"
          className="flex items-center justify-between gap-3 rounded-container border border-accent-pace/30 bg-accent-pace/5 px-5 py-4 text-sm"
        >
          <span>
            Il coach propone {proposals.data!.length === 1 ? "una modifica" : `${proposals.data!.length} modifiche`} alle
            sessioni chiave: decidi tu.
          </span>
          <span className="shrink-0 font-medium">Rivedi →</span>
        </Link>
      )}

      {plan.isError &&
        (plan.error instanceof ApiError && plan.error.status === 404 ? (
          <EmptyState
            title="Nessun piano attivo"
            description="Completa l'onboarding per ricevere il piano fino alla gara. Puoi già caricare le tue corse."
            action={
              <Link href="/onboarding" className="rounded-pill bg-fg px-5 py-2.5 text-sm font-medium text-canvas">
                Inizia l&apos;onboarding
              </Link>
            }
          />
        ) : (
          <ErrorState message={plan.error.message} onRetry={() => plan.refetch()} />
        ))}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-4 lg:col-span-2">
          {plan.isSuccess &&
            (week.isPending ? (
              <Skeleton className="h-56" />
            ) : (
              <TodayCard
                today={today}
                workouts={todayWorkouts}
                activities={weekActivities.data ?? []}
                next={nextSession}
                readiness={readiness}
                onOpen={setSelected}
              />
            ))}
          {plan.isSuccess && (
            <div className="grid grid-cols-2 gap-4">
              <WeekVolumeTile planned={plannedKm} executed={executedKm} />
              <NextKeyTile workout={nextKey} today={today} onOpen={setSelected} />
            </div>
          )}
        </div>
        <UploadCard intervalsConnected={profile.data?.intervals_connected ?? false} onUploaded={setTagging} />
      </div>

      {plan.isSuccess && monday && (
        <section className="flex flex-col gap-3">
          <h2 className="font-semibold">La settimana</h2>
          {week.isPending ? (
            <Skeleton className="h-36" />
          ) : (
            <WeekStrip
              monday={monday}
              today={today}
              workouts={week.data ?? []}
              activities={weekActivities.data ?? []}
              onOpen={setSelected}
            />
          )}
        </section>
      )}

      <LatestAnalysis activity={latest} watching={watching === latest?.id} onAnalysisStarted={setWatching} />

      <WorkoutModal workout={selected} onClose={() => setSelected(null)} />
      <ContextTagsModal activity={tagging} onClose={() => setTagging(null)} onAnalysisStarted={setWatching} />
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <Skeleton className="h-12 w-64" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Skeleton className="h-72 lg:col-span-2" />
        <Skeleton className="h-72" />
      </div>
      <Skeleton className="h-36" />
    </div>
  );
}
