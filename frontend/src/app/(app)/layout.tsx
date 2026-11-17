import { AuthGate } from "@/components/auth/AuthGate";
import { RequireProfile } from "@/components/auth/RequireProfile";
import { AppShell } from "@/components/shell/AppShell";

// The Supabase session lives only in the browser: on the server AuthGate renders its loading
// state, so instant-navigation validation can never reach the pages below. Opt out.
export const instant = false;

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <AuthGate>
      <RequireProfile>
        <AppShell>{children}</AppShell>
      </RequireProfile>
    </AuthGate>
  );
}
