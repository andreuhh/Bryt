"use client";

import { useState } from "react";

import { useToast } from "@/components/ui/Toast";
import { useAgentFeedback } from "@/lib/queries";
import type { Feedback } from "@/lib/types";

/** Alpha-tester 👍/👎 on one agent output (comment optional, suggested on 👎). */
export function FeedbackButtons({
  activityId,
  runId,
  current,
  onSent,
}: {
  activityId?: string;
  runId: string;
  current: Feedback | null | undefined;
  onSent?: (value: Feedback) => void;
}) {
  const toast = useToast();
  const feedback = useAgentFeedback(activityId);
  const [askComment, setAskComment] = useState(false);
  const [comment, setComment] = useState("");

  const send = (value: Feedback, text?: string) =>
    feedback.mutate(
      { runId, feedback: value, comment: text },
      {
        onSuccess: () => {
          onSent?.(value);
          toast(value === "UP" ? "Grazie del feedback" : "Grazie: ci aiuta a migliorare il coach", "success");
          setAskComment(false);
        },
        onError: (e) => toast(e.message, "error"),
      },
    );

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 text-xs text-fg-subtle">
        Utile?
        {(["UP", "DOWN"] as const).map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={current === value}
            aria-label={value === "UP" ? "Utile" : "Non utile"}
            disabled={feedback.isPending}
            onClick={() => (value === "DOWN" ? setAskComment(true) : send("UP"))}
            className={`rounded-pill px-2.5 py-1 text-sm transition ${
              current === value ? "bg-fg text-canvas" : "bg-elevated hover:bg-elevated-hover"
            }`}
          >
            {value === "UP" ? "👍" : "👎"}
          </button>
        ))}
      </div>
      {askComment && (
        <div className="flex flex-col gap-2">
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={2}
            maxLength={2000}
            placeholder="Cosa non torna? (facoltativo)"
            className="w-full rounded-card border border-line bg-elevated px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus:border-line-strong focus:outline-none"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => send("DOWN", comment.trim())}
              className="rounded-pill bg-fg px-3 py-1.5 text-xs font-medium text-canvas"
            >
              Invia
            </button>
            <button type="button" onClick={() => setAskComment(false)} className="px-2 text-xs text-fg-muted">
              Annulla
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
