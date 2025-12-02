"use client";

import { useConversationList } from "@/features/conversations/hooks/useConversations";
import Link from "next/link";
import { MessageSquare, Clock } from "lucide-react";
import { cn } from "@/lib/utils";

export function RecentConversations({ workspaceId }: { workspaceId: string }) {
  const { data: conversations, isLoading } = useConversationList(workspaceId);

  if (isLoading) {
      return <div className="h-12 w-full bg-muted rounded animate-pulse" />;
  }

  if (!conversations || conversations.length === 0) return null;

  return (
    <div className="w-full max-w-2xl mt-8">
        <h3 className="text-sm font-medium text-muted-foreground mb-3 px-1">Recent Conversations</h3>
        <div className="grid gap-2">
            {conversations.slice(0, 3).map((conv) => (
                <Link
                    key={conv.id}
                    href={`/workspaces/${workspaceId}/conversations/${conv.id}`}
                    className={cn(
                        "flex items-center gap-3 p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors group"
                    )}
                >
                    <div className="p-2 rounded bg-primary/10 text-primary">
                        <MessageSquare className="h-4 w-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                        <div className="font-medium truncate group-hover:text-primary transition-colors">
                            {conv.title || "Untitled Conversation"}
                        </div>
                        <div className="text-xs text-muted-foreground flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            <span>{new Date(conv.created_at || "").toLocaleDateString()}</span>
                        </div>
                    </div>
                </Link>
            ))}
        </div>
        {conversations.length > 3 && (
            <div className="mt-2 text-center">
                <span className="text-xs text-muted-foreground">
                    View all in chat history
                </span>
            </div>
        )}
    </div>
  );
}
