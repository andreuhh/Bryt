"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { type ReactNode, useEffect, useRef } from "react";

import { Wordmark } from "@/components/brand/Wordmark";
import { authEnabled, useAuth } from "@/lib/auth";

/** Private pages: render only with a Supabase session, else go to /login (and come back). */
export function AuthGate({ children }: { children: ReactNode }) {
  if (!authEnabled) return children; // local development user
  return <Gate>{children}</Gate>;
}

function Gate({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const router = useRouter();
  const client = useQueryClient();
  const userId = auth.status === "signed-in" ? auth.session.user.id : null;
  const previousUser = useRef<string | null>(null);

  useEffect(() => {
    if (auth.status !== "signed-out") return;
    const next = window.location.pathname + window.location.search;
    router.replace(`/login?next=${encodeURIComponent(next)}`);
  }, [auth.status, router]);

  // Another account in the same browser must never see the previous one's cached data
  useEffect(() => {
    if (previousUser.current && previousUser.current !== userId) client.clear();
    previousUser.current = userId;
  }, [userId, client]);

  if (auth.status !== "signed-in")
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Wordmark className="animate-pulse text-lg" />
      </div>
    );
  return children;
}
