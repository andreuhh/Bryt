import type { Metadata } from "next";

import { PlanView } from "@/components/plan/PlanView";

export const metadata: Metadata = { title: "Piano · BRYT" };

export default function PlanPage() {
  return <PlanView />;
}
