import type { Metadata } from "next";
import { Inter, Plus_Jakarta_Sans } from "next/font/google";
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

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="it"
      data-theme="dark"
      className={`${inter.variable} ${jakarta.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-canvas text-fg">{children}</body>
    </html>
  );
}
