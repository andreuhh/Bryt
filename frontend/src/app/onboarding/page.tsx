import type { Metadata } from "next";

import { OnboardingWizard } from "@/components/onboarding/OnboardingWizard";

export const metadata: Metadata = { title: "Benvenuto · BRYT" };

/** Outside the app shell: a focused, full-width wizard. */
export default function OnboardingPage() {
  return <OnboardingWizard />;
}
