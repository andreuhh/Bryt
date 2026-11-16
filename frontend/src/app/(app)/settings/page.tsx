import type { Metadata } from "next";

import { SettingsView } from "@/components/settings/SettingsView";

export const metadata: Metadata = { title: "Impostazioni · BRYT" };

export default function SettingsPage() {
  return <SettingsView />;
}
