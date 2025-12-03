"use client";

import { ReactNode } from "react";
import { ConversationSidebar } from "@/features/conversations/components/ConversationSidebar";

export default function ConversationsLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full w-full overflow-hidden">
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
         {children}
      </div>
      <ConversationSidebar />
    </div>
  );
}
