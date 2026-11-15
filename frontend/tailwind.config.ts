import type { Config } from "tailwindcss";

/**
 * BRYT Tailwind config.
 * Values are NOT defined here: every token points to a CSS Custom Property
 * declared in src/app/globals.css (single source of truth, light/dark aware).
 * Loaded from globals.css via `@config` (Tailwind v4).
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        canvas: "var(--bryt-canvas)",
        surface: "var(--bryt-surface)",
        elevated: {
          DEFAULT: "var(--bryt-elevated)",
          hover: "var(--bryt-elevated-hover)",
        },
        line: {
          DEFAULT: "var(--bryt-border)",
          strong: "var(--bryt-border-strong)",
        },
        fg: {
          DEFAULT: "var(--bryt-fg)",
          muted: "var(--bryt-fg-muted)",
          subtle: "var(--bryt-fg-subtle)",
        },
        accent: {
          pace: "var(--bryt-accent-pace)",
          load: "var(--bryt-accent-load)",
          nutrition: "var(--bryt-accent-nutrition)",
          on: "var(--bryt-on-accent)",
        },
      },
      borderColor: {
        DEFAULT: "var(--bryt-border)",
      },
      borderRadius: {
        container: "var(--bryt-radius-container)",
        card: "var(--bryt-radius-card)",
        pill: "var(--bryt-radius-pill)",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        display: ["var(--font-jakarta)", "var(--font-inter)", "sans-serif"],
      },
    },
  },
};

export default config;
