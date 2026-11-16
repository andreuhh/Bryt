import type { Metadata, Viewport } from "next";
import { Inter, Plus_Jakarta_Sans } from "next/font/google";

import { THEME_SCRIPT } from "@/components/shell/ThemeToggle";

import { Providers } from "./providers";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const jakarta = Plus_Jakarta_Sans({
  variable: "--font-jakarta",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "BRYT",
  description: "Endurance load, mechanics & recovery intelligence.",
};

export const viewport: Viewport = {
  themeColor: "#090a0c",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="it"
      data-theme="dark"
      suppressHydrationWarning
      className={`${inter.variable} ${jakarta.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full bg-canvas text-fg">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
