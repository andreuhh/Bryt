import type { Metadata } from "next";

import { ChatView } from "@/components/chat/ChatView";

export const metadata: Metadata = { title: "Coach · BRYT" };
export const instant = false; // behind AuthGate: see (app)/layout.tsx

export default function ChatPage() {
  return <ChatView />;
}
