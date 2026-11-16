"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { VolumeChart } from "@/components/charts/VolumeChart";
import { KeySessions } from "@/components/plan/KeySessions";
import { PhaseTimeline } from "@/components/plan/PhaseTimeline";
import { PlanHeader } from "@/components/plan/PlanHeader";
import { Proposals } from "@/components/plan/Proposals";
import { WeekList } from "@/components/plan/WeekList";
import { WorkoutModal } from "@/components/plan/WorkoutModal";
import { Card } from "@/components/ui/Card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { ApiError } from "@/lib/api";
import { useToday } from "@/lib/hooks";
import { planWeeks } from "@/lib/plan";
import { useActivePlan, useActivities, useProposals, useWorkouts } from "@/lib/queries";
import type { Workout } from "@/lib/types";

export function PlanView() {
  const today = useToday();
  const plan = useActivePlan();
  const ready = plan.isSuccess && today !== null;
  const workouts = useWorkouts({ from: plan.data?.start_date, to: plan.data?.end_date }, ready);
  const activities = useActivities({ from: plan.data?.start_date, to: today ?? undefined }, ready);
  const proposals = useProposals(ready);
  const [selected, setSelected] = useState<Workout | null>(null);

  const weeks = useMemo(
    () => (plan.data && workouts.data ? planWeeks(plan.data, workouts.data, activities.data ?? []) : []),
    [plan.data, workouts.data, activities.data],
  );

  if (today === null || plan.isPending) return <PlanSkeleton />;
  if (plan.isError) {
    if (plan.error instanceof ApiError && plan.error.status === 404)
      return (
        <EmptyState
          title="Nessun piano attivo"
          description="Completa l'onboarding: il coach genererà il piano fino alla tua gara obiettivo."
          action={
            <Link href="/onboarding" className="rounded-pill bg-fg px-5 py-2.5 text-sm font-medium text-canvas">
              Inizia l&apos;onboarding
            </Link>
          }
        />
      );
    return <ErrorState message={plan.error.message} onRetry={() => plan.refetch()} />;
  }

  return (
    <div className="flex flex-col gap-8">
      <PlanHeader plan={plan.data} today={today} />
      <Proposals proposals={proposals.data ?? []} />
      <PhaseTimeline plan={plan.data} today={today} />

      {workouts.isError ? (
        <ErrorState message={workouts.error.message} onRetry={() => workouts.refetch()} />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
          <Card className="flex min-w-0 flex-col lg:col-span-3">
            <h2 className="font-semibold">Volume settimanale</h2>
            <p className="mb-4 text-sm text-fg-muted">Chilometri pianificati per settimana e quelli che hai già corso.</p>
            {workouts.isPending ? <Skeleton className="h-72" /> : <VolumeChart weeks={weeks} today={today} />}
          </Card>
          <Card className="min-w-0 lg:col-span-2">
            <h2 className="font-semibold">I miei appuntamenti</h2>
            <p className="mb-4 text-sm text-fg-muted">Lunghi, lavori a passo gara, test e gare fino al via.</p>
            {workouts.isPending ? (
              <Skeleton className="h-56" />
            ) : (
              <div className="max-h-[28rem] overflow-y-auto pr-1">
                <KeySessions workouts={workouts.data} today={today} onOpen={setSelected} />
              </div>
            )}
          </Card>
        </div>
      )}

      {workouts.isSuccess && <WeekList weeks={weeks} today={today} onOpen={setSelected} />}
      <WorkoutModal workout={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function PlanSkeleton() {
  return (
    <div className="flex flex-col gap-8">
      <Skeleton className="h-28" />
      <Skeleton className="h-10" />
      <div className="grid gap-4 lg:grid-cols-5">
        <Skeleton className="h-72 lg:col-span-3" />
        <Skeleton className="h-72 lg:col-span-2" />
      </div>
    </div>
  );
}
