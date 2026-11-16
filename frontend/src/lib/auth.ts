"use client";

import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";
import { useSyncExternalStore } from "react";

/**
 * Supabase Auth, browser only. Pages are static shells with client-side data, so the session
 * lives in the browser (supabase-js storage) and every API call sends its access token.
 * Without NEXT_PUBLIC_SUPABASE_* the app falls back to the development user header.
 */
const URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

export const authEnabled = Boolean(URL && KEY);

let client: SupabaseClient | null = null;
export function supabase(): SupabaseClient {
  client ??= createClient(URL!, KEY!, { auth: { persistSession: true, autoRefreshToken: true } });
  return client;
}

export async function accessToken(): Promise<string | null> {
  if (!authEnabled) return null;
  const { data } = await supabase().auth.getSession(); // refreshes an expired token
  return data.session?.access_token ?? null;
}

// --- Session store for React --------------------------------------------------------------

export type AuthState = { status: "loading" } | { status: "signed-in"; session: Session } | { status: "signed-out" };

const LOADING: AuthState = { status: "loading" };
let state: AuthState = LOADING;
const listeners = new Set<() => void>();
let started = false;

function start() {
  if (started) return;
  started = true;
  // Fires INITIAL_SESSION right away, then on every sign-in / sign-out / token refresh
  supabase().auth.onAuthStateChange((_event, session) => {
    state = session ? { status: "signed-in", session } : { status: "signed-out" };
    listeners.forEach((l) => l());
  });
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  start();
  return () => listeners.delete(listener);
}

/** Server snapshot = loading: the session is only known in the browser. */
export function useAuth(): AuthState {
  return useSyncExternalStore(
    subscribe,
    () => state,
    () => LOADING,
  );
}

/** Per-user data kept in this browser; cleared on sign-out so the next user starts clean. */
const USER_STORAGE_KEYS = ["bryt-chat", "bryt-onboarding-draft"];

export async function signOut() {
  await supabase().auth.signOut();
  for (const key of USER_STORAGE_KEYS) {
    try {
      localStorage.removeItem(key);
    } catch {
      // storage unavailable: nothing to clear
    }
  }
}

/** Supabase error messages → Italian. */
export function authErrorMessage(error: { message: string; code?: string }): string {
  switch (error.code) {
    case "invalid_credentials":
      return "Email o password non corretti.";
    case "email_not_confirmed":
      return "Conferma prima l'indirizzo email: ti abbiamo mandato un link.";
    case "user_already_exists":
    case "email_exists":
      return "Esiste già un account con questa email. Accedi.";
    case "weak_password":
      return "Password troppo debole: usa almeno 8 caratteri.";
    case "over_email_send_rate_limit":
    case "over_request_rate_limit":
      return "Troppi tentativi. Riprova tra qualche minuto.";
    case "validation_failed":
      return "Controlla email e password.";
    default:
      return error.message;
  }
}
