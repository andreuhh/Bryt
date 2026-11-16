"use client";

import { useRouter } from "next/navigation";
import { type ReactNode, useEffect } from "react";

import { ApiError } from "@/lib/api";
import { useProfile } from "@/lib/queries";

/** A new account (no profile yet) goes straight to the onboarding wizard. */
export function RequireProfile({ children }: { children: ReactNode }) {
  const profile = useProfile();
  const router = useRouter();
  const missing = profile.error instanceof ApiError && profile.error.status === 404;

  useEffect(() => {
    if (missing) router.replace("/onboarding");
  }, [missing, router]);

  return missing ? null : children;
}
