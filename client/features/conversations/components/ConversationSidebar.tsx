"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useConversationList } from "../hooks/useConversations";

export function ConversationSidebar() {
  const params = useParams();
  const pathname = usePathname();
  const workspaceId = params.workspaceId as string;

  const { data: conversations, isLoading } = useConversationList(workspaceId);

  // If loading or no workspaceId, maybe show skeleton or nothing.
  // Requirement: "if no conversation, hide sidebar"
  if (!workspaceId) return null;
  if (isLoading) return null; // Or skeleton
  if (!conversations || conversations.length === 0) return null;

  return (
    <div className="hidden w-[260px] flex-col border-l bg-muted/10 md:flex h-full">
      <div className="flex h-14 items-center border-b px-4 font-semibold">
        Conversations
      </div>
      <ScrollArea className="flex-1">
        <div className="grid gap-1 p-2">
          {conversations.map((conv) => {
            const isActive = pathname.includes(`/conversations/${conv.id}`);
            return (
              <Link
                key={conv.id}
                href={`/workspaces/${workspaceId}/conversations/${conv.id}`}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors",
                  isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground"
                )}
              >
                <MessageSquare className="h-4 w-4" />
                <span className="truncate">{conv.title || "Untitled Conversation"}</span>
              </Link>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
