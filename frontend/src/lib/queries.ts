"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api";
import type { ChatMessage, ContextTags, Feedback, OnboardingPayload, PlanAdjustment, Surface } from "@/lib/types";

export const keys = {
  activePlan: ["plan", "active"] as const,
  workouts: (from?: string, to?: string, keyOnly = false) => ["workouts", from, to, keyOnly] as const,
  activities: (from?: string, to?: string) => ["activities", from, to] as const,
  proposals: ["plan", "proposals"] as const,
  history: (workoutId: string) => ["workouts", workoutId, "history"] as const,
  calibration: ["me", "calibration"] as const,
  me: ["me"] as const,
  profile: ["me", "profile"] as const,
  report: (activityId: string) => ["activities", activityId, "report"] as const,
  activity: (activityId: string) => ["activities", activityId] as const,
  streams: (activityId: string) => ["activities", activityId, "streams"] as const,
  personalBests: ["me", "personal-bests"] as const,
  plan: (planId: string) => ["plan", planId] as const,
  chatQuota: ["chat", "quota"] as const,
};

export function useActivePlan() {
  return useQuery({
    queryKey: keys.activePlan,
    queryFn: () => unwrap(api.GET("/api/v1/plans/active")),
    retry: (count, error) => (error as { status?: number }).status !== 404 && count < 2,
  });
}

export function useWorkouts(params: { from?: string; to?: string; keyOnly?: boolean }, enabled = true) {
  return useQuery({
    queryKey: keys.workouts(params.from, params.to, params.keyOnly),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/workouts", {
          params: { query: { from: params.from, to: params.to, key_only: params.keyOnly } },
        }),
      ),
    enabled,
  });
}

export function useActivities(params: { from?: string; to?: string; limit?: number }, enabled = true) {
  return useQuery({
    queryKey: keys.activities(params.from, params.to),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/activities", {
          params: { query: { from: params.from, to: params.to, limit: params.limit ?? 500 } },
        }),
      ),
    enabled,
  });
}

export function useProposals(enabled = true) {
  return useQuery({
    queryKey: keys.proposals,
    queryFn: () => unwrap(api.GET("/api/v1/plans/active/proposals")),
    enabled,
  });
}

export function useWorkoutHistory(workoutId: string | null) {
  return useQuery({
    queryKey: keys.history(workoutId ?? ""),
    queryFn: () =>
      unwrap(api.GET("/api/v1/workouts/{workout_id}/history", { params: { path: { workout_id: workoutId! } } })),
    enabled: Boolean(workoutId),
  });
}

export function useCalibration() {
  return useQuery({
    queryKey: keys.calibration,
    queryFn: () => unwrap(api.GET("/api/v1/me/calibration")),
  });
}

function useInvalidatePlan() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: ["plan"] });
    void client.invalidateQueries({ queryKey: ["workouts"] });
  };
}

export function useResolveProposal() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    mutationFn: ({ id, accept }: { id: string; accept: boolean }) =>
      unwrap(
        accept
          ? api.POST("/api/v1/plans/proposals/{revision_id}/accept", { params: { path: { revision_id: id } } })
          : api.POST("/api/v1/plans/proposals/{revision_id}/reject", { params: { path: { revision_id: id } } }),
      ),
    onSuccess: invalidate,
  });
}

export function useRefinePlan() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/plans/active/refine")),
    onSuccess: invalidate,
  });
}

export function useMe() {
  return useQuery({ queryKey: keys.me, queryFn: () => unwrap(api.GET("/api/v1/me")) });
}

export function useProfile() {
  return useQuery({
    queryKey: keys.profile,
    queryFn: () => unwrap(api.GET("/api/v1/me/profile")),
    retry: false,
  });
}

/** A report is complete when nutrition ran (success or error) or the first agent failed. */
export function reportComplete(report: { mechanical_load?: { status: string } | null; nutrition_recovery?: unknown } | undefined) {
  return Boolean(report?.nutrition_recovery || report?.mechanical_load?.status === "ERROR");
}

const POLL_MS = 4000;
const POLL_MAX = 75; // ~5 minutes

/** `watch`: the pipeline was just started by this client → poll until the report completes. */
export function useActivityReport(activityId: string | null, watch = false) {
  return useQuery({
    queryKey: keys.report(activityId ?? ""),
    queryFn: () =>
      unwrap(api.GET("/api/v1/activities/{activity_id}/report", { params: { path: { activity_id: activityId! } } })),
    enabled: Boolean(activityId),
    refetchInterval: (query) =>
      watch && !reportComplete(query.state.data) && query.state.dataUpdateCount < POLL_MAX ? POLL_MS : false,
  });
}

function useInvalidateActivities() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: ["activities"] });
    void client.invalidateQueries({ queryKey: ["workouts"] });
  };
}

/** Upload without analysis: the context-tags step starts it exactly once. */
export function useUploadFit() {
  const invalidate = useInvalidateActivities();
  return useMutation({
    mutationFn: (file: File) =>
      unwrap(
        api.POST("/api/v1/activities/upload-fit", {
          params: { query: { analyze: false } },
          body: { file: file as unknown as string },
          bodySerializer: (body) => {
            const form = new FormData();
            form.append("file", body.file as unknown as File);
            return form;
          },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useSaveContext() {
  const invalidate = useInvalidateActivities();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: { surface?: Surface | null; context_tags: ContextTags } }) =>
      unwrap(
        api.PATCH("/api/v1/activities/{activity_id}/context", {
          params: { path: { activity_id: id } },
          body,
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useAnalyzeInBackground() {
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.POST("/api/v1/activities/{activity_id}/analyze", {
          params: { path: { activity_id: id }, query: { background: true } },
        }),
      ),
  });
}

export function useIntervalsSync() {
  const invalidate = useInvalidateActivities();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/integrations/intervals/sync", { body: {} })),
    onSuccess: invalidate,
  });
}

export function useActivity(id: string) {
  return useQuery({
    queryKey: keys.activity(id),
    queryFn: () => unwrap(api.GET("/api/v1/activities/{activity_id}", { params: { path: { activity_id: id } } })),
  });
}

export function useActivityStreams(id: string) {
  return useQuery({
    queryKey: keys.streams(id),
    queryFn: () =>
      unwrap(api.GET("/api/v1/activities/{activity_id}/streams", { params: { path: { activity_id: id } } })),
    staleTime: Infinity, // recordings never change
  });
}

/** activityId: refreshes that activity's report; omitted for runs not tied to an activity (chat). */
export function useAgentFeedback(activityId?: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, feedback, comment }: { runId: string; feedback: Feedback; comment?: string }) =>
      unwrap(
        api.POST("/api/v1/agent-runs/{run_id}/feedback", {
          params: { path: { run_id: runId } },
          body: { feedback, comment: comment || null },
        }),
      ),
    onSuccess: () => {
      if (activityId) void client.invalidateQueries({ queryKey: keys.report(activityId) });
    },
  });
}

export function usePersonalBests() {
  return useQuery({ queryKey: keys.personalBests, queryFn: () => unwrap(api.GET("/api/v1/me/personal-bests")) });
}

export function useSubmitOnboarding() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: OnboardingPayload) => unwrap(api.PUT("/api/v1/me/onboarding", { body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["me"] }),
  });
}

export function useGeneratePlan() {
  return useMutation({ mutationFn: () => unwrap(api.POST("/api/v1/plans/generate", { body: {} })) });
}

/** Polls a plan while the background generation runs (GENERATING → ACTIVE | FAILED). */
export function usePlanGeneration(planId: string | null) {
  return useQuery({
    queryKey: keys.plan(planId ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/plans/{plan_id}", { params: { path: { plan_id: planId! } } })),
    enabled: Boolean(planId),
    refetchInterval: (query) => (query.state.data?.status === "GENERATING" || !query.state.data ? 5000 : false),
  });
}

export function useChatQuota() {
  return useQuery({ queryKey: keys.chatQuota, queryFn: () => unwrap(api.GET("/api/v1/chat/quota")) });
}

export function useCoachChat() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (messages: ChatMessage[]) => unwrap(api.POST("/api/v1/chat", { body: { messages } })),
    onSuccess: (res) => client.setQueryData(keys.chatQuota, res.quota),
    onError: () => void client.invalidateQueries({ queryKey: keys.chatQuota }),
  });
}

export function useApplyAdjustment() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    mutationFn: (adjustment: PlanAdjustment) => unwrap(api.POST("/api/v1/plans/adjust", { body: { adjustment } })),
    onSuccess: invalidate,
  });
}
