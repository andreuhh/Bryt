"use client";

import { type ReactNode, useEffect, useRef } from "react";

import { IconX } from "@/components/icons";

/** Native <dialog>: focus trap, Esc and backdrop for free. Bottom sheet on mobile. */
export function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className="m-0 mt-auto w-full max-w-none rounded-t-container border border-line bg-surface p-0 text-fg backdrop:bg-black/60 backdrop:backdrop-blur-sm sm:m-auto sm:max-w-lg sm:rounded-container"
    >
      <div className="flex items-center justify-between border-b border-line px-6 py-4">
        <h2 className="font-display text-lg font-semibold">{title}</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Chiudi"
          className="rounded-pill p-2 text-fg-muted hover:bg-elevated hover:text-fg"
        >
          <IconX />
        </button>
      </div>
      <div className="max-h-[75vh] overflow-y-auto px-6 py-5">{children}</div>
    </dialog>
  );
}
