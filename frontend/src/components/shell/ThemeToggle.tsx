"use client";

import { useSyncExternalStore } from "react";

import { IconMoon, IconSun } from "@/components/icons";

export const THEME_KEY = "bryt-theme";

/** Runs in <head> before first paint: applies the saved theme (default dark), no flash. */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_KEY}");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}})()`;

function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}

const getTheme = () => document.documentElement.getAttribute("data-theme") ?? "dark";

export function ThemeToggle({ className = "" }: { className?: string }) {
  const theme = useSyncExternalStore(subscribe, getTheme, () => "dark");
  const next = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      onClick={() => {
        document.documentElement.setAttribute("data-theme", next);
        try {
          localStorage.setItem(THEME_KEY, next);
        } catch {
          /* storage unavailable: theme still applies for this session */
        }
      }}
      aria-label={next === "light" ? "Passa al tema chiaro" : "Passa al tema scuro"}
      className={`rounded-pill p-2.5 text-fg-muted transition hover:bg-elevated hover:text-fg ${className}`}
    >
      {theme === "dark" ? <IconSun /> : <IconMoon />}
    </button>
  );
}
