"use client";

import type { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

import { Pill } from "@/components/ui/Pill";

const inputClass =
  "h-11 w-full rounded-card border border-line bg-elevated px-4 text-sm text-fg placeholder:text-fg-subtle focus:border-line-strong focus:outline-none aria-[invalid=true]:border-accent-load";

export function Field({
  label,
  hint,
  error,
  required,
  children,
}: {
  label: string;
  hint?: ReactNode;
  error?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium uppercase tracking-wider text-fg-subtle">
        {label}
        {required && (
          <span className="ml-0.5 text-fg" aria-label="obbligatorio">
            *
          </span>
        )}
      </p>
      {children}
      {error ? (
        <p className="text-xs text-accent-load" role="alert">
          {error}
        </p>
      ) : (
        hint && <p className="text-xs text-fg-subtle">{hint}</p>
      )}
    </div>
  );
}

export function TextInput({ invalid, className = "", ...props }: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return <input aria-invalid={invalid || undefined} className={`${inputClass} ${className}`} {...props} />;
}

export function NumberInput(props: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return <TextInput type="number" inputMode="decimal" {...props} />;
}

export function TextArea({ className = "", ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={`w-full rounded-card border border-line bg-elevated px-4 py-3 text-sm text-fg placeholder:text-fg-subtle focus:border-line-strong focus:outline-none ${className}`}
      {...props}
    />
  );
}

/** h : m : s as three small numeric inputs (race times, PBs). */
export function DurationInput({
  value,
  onChange,
  invalid,
  label,
}: {
  value: { h: string; m: string; s: string };
  onChange: (value: { h: string; m: string; s: string }) => void;
  invalid?: boolean;
  label: string;
}) {
  const part = (key: "h" | "m" | "s", placeholder: string, max: number) => (
    <TextInput
      type="number"
      inputMode="numeric"
      min={0}
      max={max}
      placeholder={placeholder}
      aria-label={`${label}: ${placeholder}`}
      value={value[key]}
      invalid={invalid}
      onChange={(e) => onChange({ ...value, [key]: e.target.value })}
      className="w-20 text-center"
    />
  );
  return (
    <div className="flex items-center gap-2">
      {part("h", "ore", 23)}
      <span className="text-fg-subtle">:</span>
      {part("m", "min", 59)}
      <span className="text-fg-subtle">:</span>
      {part("s", "sec", 59)}
    </div>
  );
}

/** Multi-select as toggle pills. */
export function MultiPills<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[];
  value: T[];
  onChange: (value: T[]) => void;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((o) => {
        const on = value.includes(o.value);
        return (
          <Pill
            key={o.value}
            aria-pressed={on}
            active={on}
            onClick={() => onChange(on ? value.filter((v) => v !== o.value) : [...value, o.value])}
          >
            {o.label}
          </Pill>
        );
      })}
    </div>
  );
}
