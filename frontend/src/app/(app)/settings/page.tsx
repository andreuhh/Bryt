import type { Metadata } from "next";

import { SettingsView } from "@/components/settings/SettingsView";

export const metadata: Metadata = { title: "Impostazioni · BRYT" };
export const instant = false; // behind AuthGate: see (app)/layout.tsx

export default function SettingsPage() {
  return <SettingsView />;
}
