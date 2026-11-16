"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, Suspense } from "react";

import { SignOutButton } from "@/components/auth/SignOutButton";
import { Wordmark } from "@/components/brand/Wordmark";
import { IconCalendar, IconChat, IconGrid, IconSettings } from "@/components/icons";
import { ThemeToggle } from "@/components/shell/ThemeToggle";

const NAV = [
  { href: "/dashboard", label: "Dashboard", Icon: IconGrid },
  { href: "/plan", label: "Piano", Icon: IconCalendar },
  { href: "/chat", label: "Coach", Icon: IconChat },
  { href: "/settings", label: "Impostazioni", Icon: IconSettings },
] as const;

type NavProps = { pathname: string | null };

const isActive = (pathname: string | null, href: string) =>
  pathname !== null && (pathname === href || pathname.startsWith(`${href}/`));

function SideNav({ pathname }: NavProps) {
  return (
    <nav className="mt-10 flex flex-col gap-1">
      {NAV.map(({ href, label, Icon }) => (
        <Link
          key={href}
          href={href}
          aria-current={isActive(pathname, href) ? "page" : undefined}
          className={`flex items-center gap-3 rounded-pill px-4 py-2.5 text-sm font-medium transition ${
            isActive(pathname, href) ? "bg-elevated text-fg" : "text-fg-muted hover:bg-elevated/60 hover:text-fg"
          }`}
        >
          <Icon />
          {label}
        </Link>
      ))}
    </nav>
  );
}

function BottomNav({ pathname }: NavProps) {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-20 flex justify-around border-t border-line bg-canvas/90 px-2 pb-[max(env(safe-area-inset-bottom),0.5rem)] pt-2 backdrop-blur md:hidden">
      {NAV.map(({ href, label, Icon }) => (
        <Link
          key={href}
          href={href}
          aria-current={isActive(pathname, href) ? "page" : undefined}
          className={`flex flex-col items-center gap-0.5 rounded-card px-2 py-1.5 text-[11px] font-medium ${
            isActive(pathname, href) ? "text-fg" : "text-fg-subtle"
          }`}
        >
          <Icon />
          {label}
        </Link>
      ))}
    </nav>
  );
}

/** usePathname() is request data on dynamic routes (e.g. /activity/[id]): under Cache
 * Components it must sit inside <Suspense>; the fallback renders the nav without highlight. */
function WithPathname({ render }: { render: (props: NavProps) => ReactNode }) {
  const pathname = usePathname();
  return render({ pathname });
}

function ActiveNav({ render }: { render: (props: NavProps) => ReactNode }) {
  return (
    <Suspense fallback={render({ pathname: null })}>
      <WithPathname render={render} />
    </Suspense>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-line px-4 py-6 md:flex">
        <Link href="/dashboard" className="px-3">
          <Wordmark className="text-lg" />
        </Link>
        <ActiveNav render={(p) => <SideNav {...p} />} />
        <div className="mt-auto flex items-center justify-between">
          <SignOutButton className="px-3 text-xs" />
          <ThemeToggle />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center justify-between border-b border-line bg-canvas/85 px-4 py-3 backdrop-blur md:hidden">
          <Wordmark className="text-base" />
          <ThemeToggle />
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-28 pt-6 sm:px-6 md:pb-12 md:pt-10">
          {children}
        </main>

        <ActiveNav render={(p) => <BottomNav {...p} />} />
      </div>
    </div>
  );
}
