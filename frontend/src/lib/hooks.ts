"use client";

import { useSyncExternalStore } from "react";

import { today } from "@/lib/format";

const noopSubscribe = () => () => {};

/**
 * Today's local date (Europe/Rome), read in the browser only. Under Cache Components the
 * current time cannot be read while prerendering, so the server snapshot is null and
 * callers render their loading state until hydration.
 */
export function useToday(): string | null {
  return useSyncExternalStore(noopSubscribe, today, () => null);
}
