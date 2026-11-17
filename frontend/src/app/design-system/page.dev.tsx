import type { Metadata } from "next";

import { DesignSystemView } from "./DesignSystemView";

export const metadata: Metadata = { title: "Design system · BRYT" };

/** Development only: `.dev.tsx` pages are recognized by `next dev` alone (next.config.ts). */
export default function DesignSystemPage() {
  return <DesignSystemView />;
}
