import type { Metadata } from "next";
import { Suspense } from "react";

import { ActivityView } from "@/components/activity/ActivityView";
import { Skeleton } from "@/components/ui/States";

export const metadata: Metadata = { title: "Attività · BRYT" };

/** The activity id is request data (not prerenderable): the view reads it under Suspense. */
export default function ActivityPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <ActivityView />
    </Suspense>
  );
}
