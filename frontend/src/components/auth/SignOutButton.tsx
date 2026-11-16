"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { authEnabled, signOut } from "@/lib/auth";

export function SignOutButton({ className = "" }: { className?: string }) {
  const router = useRouter();
  const client = useQueryClient();
  if (!authEnabled) return null;
  return (
    <button
      type="button"
      onClick={async () => {
        await signOut();
        client.clear();
        router.replace("/login");
      }}
      className={`text-fg-subtle hover:text-fg ${className || "text-xs"}`}
    >
      Esci
    </button>
  );
}
