import { AuthGate } from "@/components/auth/AuthGate";
import { RequireProfile } from "@/components/auth/RequireProfile";
import { AppShell } from "@/components/shell/AppShell";

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <AuthGate>
      <RequireProfile>
        <AppShell>{children}</AppShell>
      </RequireProfile>
    </AuthGate>
  );
}
