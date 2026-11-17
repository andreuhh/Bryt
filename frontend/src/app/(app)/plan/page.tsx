import type { Metadata } from "next";

import { PlanView } from "@/components/plan/PlanView";

export const metadata: Metadata = { title: "Piano · BRYT" };
export const instant = false; // behind AuthGate: see (app)/layout.tsx

export default function PlanPage() {
  return <PlanView />;
}
