"use client";

import Link from "next/link";
import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";

import { FeedbackButtons } from "@/components/activity/FeedbackButtons";
import { ProposalCard } from "@/components/chat/ProposalCard";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { ApiError } from "@/lib/api";
import { type ChatTurn, chatErrorMessage, loadChat, MAX_CHARS, saveChat, SUGGESTIONS, toRequest } from "@/lib/chat";
import { useActivePlan, useChatQuota, useCoachChat } from "@/lib/queries";

export function ChatView() {
  const plan = useActivePlan();
  const chat = useCoachChat();
  const quota = useChatQuota();
  const [turns, setTurns] = useState<ChatTurn[] | null>(null);
  const [input, setInput] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time read of browser storage
    setTurns(loadChat());
  }, []);

  useEffect(() => {
    if (turns) saveChat(turns);
  }, [turns]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns?.length, plan.isPending, chat.isPending, chat.isError]);

  if (turns === null || plan.isPending) return <Skeleton className="h-96" />;

  if (plan.isError && !(plan.error instanceof ApiError && plan.error.status === 404))
    return <ErrorState message={plan.error.message} onRetry={() => plan.refetch()} />;
  if (plan.isError)
    return (
      <EmptyState
        title="Prima serve un piano"
        description="Il coach risponde partendo dal tuo profilo, dal piano e dalle ultime corse."
        action={
          <Link href="/onboarding" className="rounded-pill bg-fg px-5 py-2.5 text-sm font-medium text-canvas">
            Inizia l&apos;onboarding
          </Link>
        }
      />
    );

  const send = (conversation: ChatTurn[]) =>
    chat.mutate(toRequest(conversation), {
      onSuccess: (res) =>
        setTurns((t) => [
          ...(t ?? []),
          {
            role: "assistant",
            content: res.reply,
            runId: res.agent_run_id,
            proposal: res.proposed_adjustment ?? undefined,
          },
        ]),
    });

  const exhausted = quota.data?.remaining === 0;

  const submit = (text: string) => {
    const content = text.trim();
    if (!content || chat.isPending || exhausted) return;
    const next: ChatTurn[] = [...turns, { role: "user", content }];
    setTurns(next);
    setInput("");
    send(next);
  };

  const update = (index: number, patch: Partial<ChatTurn>) =>
    setTurns((t) => (t ?? []).map((turn, i) => (i === index ? { ...turn, ...patch } : turn)));

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit(input);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit(input);
    }
  };

  return (
    <div className="mx-auto flex min-h-[calc(100dvh-14rem)] w-full max-w-3xl flex-col gap-6 md:min-h-[calc(100dvh-5.5rem)]">
      <header className="flex flex-col gap-1">
        <div className="flex items-center justify-between gap-4">
          <h1 className="text-3xl font-bold">Coach</h1>
          {turns.length > 0 && (
            <Button size="sm" variant="ghost" disabled={chat.isPending} onClick={() => (setTurns([]), chat.reset())}>
              Nuova conversazione
            </Button>
          )}
        </div>
        <p className="text-sm text-fg-muted">
          Conosce profilo, piano dei prossimi 14 giorni e ultime corse. Può proporre modifiche, che applichi tu.
        </p>
      </header>

      {turns.length === 0 && (
        <div className="flex flex-col gap-3">
          <p className="text-xs uppercase tracking-wider text-fg-subtle">Per iniziare</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                disabled={exhausted}
                onClick={() => submit(s)}
                className="rounded-card border border-line bg-surface px-4 py-3 text-left text-sm text-fg-muted transition hover:border-line-strong hover:text-fg disabled:pointer-events-none disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      <ol className="flex flex-col gap-5" aria-live="polite">
        {turns.map((turn, i) =>
          turn.role === "user" ? (
            <li key={i} className="flex justify-end">
              <p className="max-w-[85%] whitespace-pre-line rounded-card rounded-br-md bg-elevated px-4 py-2.5 text-sm text-fg">
                {turn.content}
              </p>
            </li>
          ) : (
            <li key={i} className="flex flex-col gap-3">
              <p className="text-xs font-medium uppercase tracking-wider text-fg-subtle">Coach</p>
              <p className="whitespace-pre-line text-[15px] leading-relaxed text-fg">{turn.content}</p>
              {turn.proposal && (
                <ProposalCard
                  proposal={turn.proposal}
                  outcome={turn.outcome}
                  onOutcome={(outcome) => update(i, { outcome })}
                />
              )}
              {turn.runId && (
                <FeedbackButtons
                  runId={turn.runId}
                  current={turn.feedback}
                  onSent={(feedback) => update(i, { feedback })}
                />
              )}
            </li>
          ),
        )}
        {chat.isPending && (
          <li className="flex items-center gap-2 text-sm text-fg-subtle">
            <span className="size-4 animate-spin rounded-full border-2 border-fg-subtle border-t-transparent" />
            Il coach sta guardando i tuoi dati…
          </li>
        )}
      </ol>

      {chat.isError && <ErrorState message={chatErrorMessage(chat.error)} onRetry={() => send(turns)} />}

      <div ref={bottom} />

      <div className="sticky bottom-16 -mx-4 mt-auto bg-canvas px-4 pb-4 pt-2 sm:-mx-6 sm:px-6 md:bottom-0 md:pb-6">
        <form onSubmit={onSubmit} className="flex items-end gap-2 rounded-container border border-line bg-surface p-2">
          <label htmlFor="chat-input" className="sr-only">
            Scrivi al coach
          </label>
          <textarea
            id="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            maxLength={MAX_CHARS}
            disabled={exhausted}
            placeholder={exhausted ? "Messaggi di oggi esauriti" : "Scrivi al coach…"}
            className="max-h-40 min-h-11 flex-1 resize-none bg-transparent px-3 py-3 text-sm text-fg [field-sizing:content] placeholder:text-fg-subtle focus:outline-none"
          />
          <Button type="submit" loading={chat.isPending} disabled={!input.trim() || exhausted}>
            Invia
          </Button>
        </form>
        {quota.data && (
          <p className="mt-2 px-4 text-xs text-fg-subtle">
            {exhausted
              ? `Hai usato i ${quota.data.limit} messaggi di oggi: il coach torna disponibile domani.`
              : `${quota.data.remaining} di ${quota.data.limit} messaggi rimasti oggi`}
          </p>
        )}
      </div>
    </div>
  );
}
