"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Wordmark } from "@/components/brand/Wordmark";
import { ReviewZones } from "@/components/onboarding/Finish";
import {
  StepAthlete,
  StepGoal,
  StepLifestyle,
  StepMethod,
  StepResults,
  StepTraining,
} from "@/components/onboarding/Steps";
import { Button } from "@/components/ui/Button";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { ApiError } from "@/lib/api";
import { useToday } from "@/lib/hooks";
import {
  clearDraft,
  type Draft,
  EMPTY_DRAFT,
  type Errors,
  fromProfile,
  loadDraft,
  saveDraft,
  toPayload,
  validateStep,
} from "@/lib/onboarding";
import { useActivePlan, useMe, usePersonalBests, useProfile, useSubmitOnboarding } from "@/lib/queries";

const STEPS = [
  { title: "Chi sei", subtitle: "Il punto di partenza del coach." },
  { title: "I tuoi risultati", subtitle: "Da qui si calcolano le tue zone di passo." },
  { title: "L'obiettivo", subtitle: "La gara verso cui costruiamo il piano." },
  { title: "La tua settimana", subtitle: "Il piano si adatta alla tua vita, non il contrario." },
  { title: "Come ti alleni", subtitle: "Volume, forza e vincoli." },
  { title: "Metodo e dati", subtitle: "Ultimo passo." },
] as const;

const REVIEW = STEPS.length;

export function OnboardingWizard() {
  const today = useToday();
  const me = useMe();
  const profile = useProfile();
  const savedPbs = usePersonalBests();
  const activePlan = useActivePlan();
  const submit = useSubmitOnboarding();

  const [draft, setDraft] = useState<Draft | null>(null);
  const [step, setStep] = useState(0);
  const [errors, setErrors] = useState<Errors>({});
  const top = useRef<HTMLDivElement>(null);

  // Initial draft: resume the browser draft, else pre-fill from an existing profile
  useEffect(() => {
    if (draft || profile.isPending || me.isPending) return;
    const resumed = loadDraft();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time initialisation from async data
    setDraft(resumed ?? (profile.data ? fromProfile(profile.data, me.data) : EMPTY_DRAFT));
  }, [draft, profile.isPending, profile.data, me.isPending, me.data]);

  useEffect(() => {
    if (draft) saveDraft(draft);
  }, [draft]);

  if (!draft || today === null) return <Skeleton className="h-96" />;

  const set = (patch: Partial<Draft>) => {
    setDraft((d) => ({ ...(d ?? EMPTY_DRAFT), ...patch }));
    setErrors({});
  };
  const scrollTop = () => top.current?.scrollIntoView({ behavior: "smooth", block: "start" });

  const next = () => {
    const e = validateStep(step, draft, savedPbs.data ?? [], today);
    setErrors(e);
    if (Object.keys(e).length) return;
    if (step < STEPS.length - 1) {
      setStep(step + 1);
      scrollTop();
      return;
    }
    submit.mutate(toPayload(draft), {
      onSuccess: () => {
        clearDraft();
        setStep(REVIEW);
        scrollTop();
      },
    });
  };

  const props = { d: draft, set, errors };
  const hasActivePlan = activePlan.isSuccess;

  return (
    <div ref={top} className="mx-auto flex w-full max-w-2xl flex-col gap-8 px-4 py-8 sm:py-12">
      <header className="flex items-center justify-between">
        <Wordmark className="text-base" />
        {profile.data && (
          <Link href="/dashboard" className="text-sm text-fg-muted hover:text-fg">
            Esci
          </Link>
        )}
      </header>

      {step < REVIEW ? (
        <>
          <div className="flex flex-col gap-3">
            <div className="flex gap-1.5" aria-hidden>
              {STEPS.map((s, i) => (
                <span key={s.title} className={`h-1 flex-1 rounded-pill ${i <= step ? "bg-accent-pace" : "bg-elevated"}`} />
              ))}
            </div>
            <p className="text-xs uppercase tracking-wider text-fg-subtle">
              Passo {step + 1} di {STEPS.length}
            </p>
            <h1 className="text-3xl font-bold">{STEPS[step].title}</h1>
            <p className="text-fg-muted">{STEPS[step].subtitle}</p>
          </div>

          {step === 0 && <StepAthlete {...props} />}
          {step === 1 && <StepResults {...props} saved={savedPbs.data ?? []} />}
          {step === 2 && <StepGoal {...props} />}
          {step === 3 && <StepLifestyle {...props} />}
          {step === 4 && <StepTraining {...props} />}
          {step === 5 && <StepMethod {...props} />}

          {Object.keys(errors).length > 0 && (
            <p className="text-sm text-accent-load" role="alert">
              Controlla i campi evidenziati.
            </p>
          )}
          {submit.isError && (
            <ErrorState
              message={
                submit.error instanceof ApiError && submit.error.status === 422
                  ? `Dati non accettati: ${submit.error.message}`
                  : submit.error.message
              }
            />
          )}

          <div className="sticky bottom-0 -mx-4 flex justify-between gap-3 border-t border-line bg-canvas/90 px-4 py-4 backdrop-blur">
            {step > 0 ? (
              <Button variant="ghost" onClick={() => (setStep(step - 1), setErrors({}), scrollTop())}>
                Indietro
              </Button>
            ) : (
              <span />
            )}
            <Button onClick={next} loading={submit.isPending}>
              {step === STEPS.length - 1 ? "Salva e calcola le zone" : "Avanti"}
            </Button>
          </div>
        </>
      ) : (
        <>
          <div className="flex flex-col gap-2">
            <h1 className="text-3xl font-bold">Le tue zone</h1>
            <p className="text-fg-muted">Calcolate dai tuoi risultati. Il piano userà questi passi.</p>
          </div>
          <ReviewZones hasActivePlan={hasActivePlan} onBack={() => setStep(0)} />
        </>
      )}
    </div>
  );
}
