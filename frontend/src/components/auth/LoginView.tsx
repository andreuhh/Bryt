"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { type FormEvent, type ReactNode, useEffect, useState } from "react";

import { Wordmark } from "@/components/brand/Wordmark";
import { Button } from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { ErrorState } from "@/components/ui/States";
import { authEnabled, authErrorMessage, supabase, useAuth } from "@/lib/auth";

type Mode = "sign-in" | "sign-up";

const MIN_PASSWORD = 8;

/** Only same-site paths: never redirect to another origin after login. */
function nextPath(): string {
  const next = new URLSearchParams(window.location.search).get("next");
  return next?.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
}

export function LoginView() {
  const auth = useAuth();
  const router = useRouter();
  const client = useQueryClient();
  const [mode, setMode] = useState<Mode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [confirmSent, setConfirmSent] = useState(false);

  // Signed in (also right after clicking the email confirmation link): go on
  useEffect(() => {
    if (auth.status !== "signed-in") return;
    client.clear();
    router.replace(nextPath());
  }, [auth.status, client, router]);

  if (!authEnabled)
    return (
      <Shell>
        <p className="text-sm text-fg-muted">
          Login non configurato: in sviluppo l&apos;app usa l&apos;utente locale. Imposta{" "}
          <code className="text-fg">NEXT_PUBLIC_SUPABASE_URL</code> e{" "}
          <code className="text-fg">NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY</code> in{" "}
          <code className="text-fg">.env.local</code>.
        </p>
      </Shell>
    );

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (mode === "sign-up" && password.length < MIN_PASSWORD) {
      setError(`La password deve avere almeno ${MIN_PASSWORD} caratteri.`);
      return;
    }
    setPending(true);
    const credentials = { email: email.trim(), password };
    const { data, error: authError } =
      mode === "sign-in"
        ? await supabase().auth.signInWithPassword(credentials)
        : await supabase().auth.signUp({
            ...credentials,
            options: { emailRedirectTo: `${window.location.origin}/login` },
          });
    setPending(false);
    if (authError) setError(authErrorMessage(authError));
    // Sign-up with email confirmation on: no session until the link is clicked
    else if (mode === "sign-up" && !data.session) setConfirmSent(true);
  };

  if (confirmSent)
    return (
      <Shell>
        <h1 className="text-3xl font-bold">Controlla la tua email</h1>
        <p className="text-fg-muted">
          Abbiamo mandato un link di conferma a <span className="text-fg">{email.trim()}</span>. Aprilo da questo
          dispositivo per entrare.
        </p>
        <button
          type="button"
          onClick={() => (setConfirmSent(false), setMode("sign-in"))}
          className="self-start text-sm text-fg-muted underline-offset-4 hover:text-fg hover:underline"
        >
          Torna all&apos;accesso
        </button>
      </Shell>
    );

  return (
    <Shell>
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-bold">{mode === "sign-in" ? "Bentornato" : "Crea il tuo account"}</h1>
        <p className="text-fg-muted">
          {mode === "sign-in" ? "Accedi per vedere piano, corse e analisi." : "Poi ti chiediamo qualche dato per le tue zone."}
        </p>
      </div>
      <SegmentedControl
        label="Accesso"
        value={mode}
        onChange={(m) => (setMode(m), setError(null))}
        options={[
          { value: "sign-in", label: "Accedi" },
          { value: "sign-up", label: "Registrati" },
        ]}
      />
      <form onSubmit={submit} className="flex flex-col gap-5">
        <Field label="Email" required>
          <TextInput
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field label="Password" required hint={mode === "sign-up" ? `Almeno ${MIN_PASSWORD} caratteri.` : undefined}>
          <TextInput
            type="password"
            autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        {error && <ErrorState message={error} />}
        <Button type="submit" loading={pending || auth.status === "signed-in"}>
          {mode === "sign-in" ? "Accedi" : "Crea account"}
        </Button>
      </form>
    </Shell>
  );
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-sm flex-col justify-center gap-8 px-4 py-12">
      <Wordmark className="text-base" />
      {children}
    </div>
  );
}
