import { ApiError } from "@/lib/api";
import type { ChatMessage, Feedback, PlanAdjustment, PlanAdjustResult } from "@/lib/types";

/** One bubble. Coach turns carry the agent run (feedback) and an optional plan proposal. */
export type ChatTurn = {
  role: "user" | "assistant";
  content: string;
  runId?: string;
  feedback?: Feedback;
  proposal?: PlanAdjustment;
  /** What happened to the proposal: applied (with the result) or dismissed. */
  outcome?: { applied: PlanAdjustResult } | "dismissed";
};

/** Backend limits (ChatRequest): 40 messages, 4000 characters each. */
export const MAX_MESSAGES = 40;
export const MAX_CHARS = 4000;

export const SUGGESTIONS = [
  "Com'è andata la mia ultima corsa?",
  "Ho dormito male: cosa cambio domani?",
  "Sono in viaggio da giovedì a sabato",
  "Ho un fastidio al polpaccio destro",
];

/** The coach is stateless: send the latest turns, starting from a user message. */
export function toRequest(turns: ChatTurn[]): ChatMessage[] {
  const recent = turns.slice(-MAX_MESSAGES);
  const first = recent.findIndex((t) => t.role === "user");
  return recent.slice(Math.max(first, 0)).map(({ role, content }) => ({ role, content }));
}

export function chatErrorMessage(error: Error): string {
  if (!(error instanceof ApiError)) return error.message;
  if (error.status === 0) return error.message;
  if (error.status === 409) return "Completa l'onboarding e genera un piano: il coach parte da lì.";
  if (error.status === 429) return "Hai usato tutti i messaggi di oggi: il coach torna disponibile domani.";
  if (error.status === 422) return "Il coach non può rispondere a questa richiesta. Prova a riformularla.";
  if (error.status === 503) return "Il coach non è raggiungibile in questo momento. Riprova tra poco.";
  return "Il coach non ha risposto correttamente. Riprova.";
}

export function adjustErrorMessage(error: Error): string {
  if (error instanceof ApiError && error.status === 409)
    return "Nessun allenamento da modificare nei prossimi giorni, oppure non c'è un piano attivo.";
  return chatErrorMessage(error);
}

// --- Per-browser persistence (convenience only: the backend keeps no conversation) -------

const CHAT_KEY = "bryt-chat";

export function loadChat(): ChatTurn[] {
  try {
    const raw = localStorage.getItem(CHAT_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed as ChatTurn[]) : [];
  } catch {
    return [];
  }
}

export function saveChat(turns: ChatTurn[]) {
  try {
    if (turns.length) localStorage.setItem(CHAT_KEY, JSON.stringify(turns));
    else localStorage.removeItem(CHAT_KEY);
  } catch {
    // storage unavailable: the conversation just won't survive a reload
  }
}
