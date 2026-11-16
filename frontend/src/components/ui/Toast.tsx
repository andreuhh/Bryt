"use client";

import { createContext, type ReactNode, useCallback, useContext, useState } from "react";

type Tone = "neutral" | "success" | "error";
type ToastItem = { id: number; message: string; tone: Tone };

const ToastContext = createContext<(message: string, tone?: Tone) => void>(() => {});

const tones: Record<Tone, string> = {
  neutral: "border-line",
  success: "border-accent-pace/40",
  error: "border-accent-load/50",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const push = useCallback((message: string, tone: Tone = "neutral") => {
    const id = Date.now() + Math.random();
    setItems((list) => [...list, { id, message, tone }]);
    setTimeout(() => setItems((list) => list.filter((t) => t.id !== id)), 5000);
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-4 bottom-24 z-50 flex flex-col items-center gap-2 md:bottom-6 md:left-auto md:right-6 md:items-end"
      >
        {items.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto max-w-sm rounded-card border bg-surface px-4 py-3 text-sm text-fg shadow-2xl ${tones[t.tone]}`}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
