import type { Metadata } from "next";

import { DashboardView } from "@/components/dashboard/DashboardView";

export const metadata: Metadata = { title: "Dashboard · BRYT" };
export const instant = false; // behind AuthGate: see (app)/layout.tsx

export default function DashboardPage() {
  return <DashboardView />;
}
