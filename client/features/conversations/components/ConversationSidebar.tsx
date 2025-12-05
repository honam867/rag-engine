"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useConversationList } from "../hooks/useConversations";
import { DocumentSidebar } from "@/features/documents/components/DocumentSidebar";

export function ConversationSidebar() {
  const params = useParams();
  const pathname = usePathname();
  const workspaceId = params.workspaceId as string;

  const { data: conversations, isLoading } = useConversationList(workspaceId);

  if (!workspaceId) return null;

  return (
    <div className="hidden w-[300px] flex-col border-l bg-muted/10 md:flex h-full">
      
      {/* Top Half: Conversations */}
      <div className="flex flex-col h-1/2 min-h-0 border-b">
          <div className="flex h-14 items-center border-b px-4 font-semibold shrink-0">
            Conversations
          </div>
          <ScrollArea className="flex-1">
            <div className="grid gap-1 p-2">
              {isLoading && (
                  <div className="p-4 text-sm text-muted-foreground text-center">Loading chats...</div>
              )}
              
              {!isLoading && conversations?.length === 0 && (
                   <div className="p-4 text-sm text-muted-foreground text-center">No conversations yet.</div>
              )}

              {conversations?.map((conv) => {
                const isActive = pathname.includes(`/conversations/${conv.id}`);
                return (
                  <Link
                    key={conv.id}
                    href={`/workspaces/${workspaceId}/conversations/${conv.id}`}
                    className={cn(
                      "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors min-w-0",
                      isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground"
                    )}
                    title={conv.title || "Untitled Conversation"}
                  >
                    <MessageSquare className="h-4 w-4 shrink-0" />
                    <span className="truncate pr-2 flex-1">{conv.title || "Untitled Conversation"}</span>
                  </Link>
                );
              })}
            </div>
          </ScrollArea>
      </div>

      {/* Bottom Half: Documents */}
      <div className="flex flex-col h-1/2 min-h-0">
         <DocumentSidebar workspaceId={workspaceId} className="h-full border-l-0 border-t-0 bg-transparent" />
      </div>

    </div>
  );
}
