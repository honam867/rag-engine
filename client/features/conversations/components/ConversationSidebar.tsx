"use client";

import Link from "next/link";
import { useState } from "react";
import { useParams, usePathname, useRouter } from "next/navigation";
import { MessageSquare, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useConversationList, useDeleteConversation } from "../hooks/useConversations";
import { DocumentSidebar } from "@/features/documents/components/DocumentSidebar";
import { Button } from "@/components/ui/button";
import { DeleteConfirmDialog } from "@/components/ui/delete-confirm-dialog";
import { toast } from "sonner";
import { ROUTES } from "@/lib/routes";

export function ConversationSidebar() {
  const params = useParams();
  const pathname = usePathname();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;

  const { data: conversations, isLoading } = useConversationList(workspaceId);
  const { mutateAsync: deleteConversation, isPending: isDeleting } = useDeleteConversation(workspaceId);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const handleDelete = async () => {
    if (!deleteId) return;
    try {
      await deleteConversation(deleteId);
      toast.success("Conversation deleted");
      
      // If deleting current active conversation, redirect to workspace root
      if (pathname.includes(`/conversations/${deleteId}`)) {
        router.push(ROUTES.workspaceDetail(workspaceId));
      }
    } catch (error) {
      toast.error("Failed to delete conversation");
    } finally {
      setDeleteId(null);
    }
  };

  if (!workspaceId) return null;

  return (
    <div className="hidden w-[300px] flex-col border-l bg-muted/10 md:flex h-full shrink-0">
      
      {/* Top Half: Conversations */}
      <div className="flex flex-col h-1/2 min-h-0 border-b">
          <div className="flex h-14 items-center border-b px-4 font-semibold shrink-0 bg-muted/20">
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
                  <div key={conv.id} className="group relative w-full flex items-center pr-9 rounded-md hover:bg-accent hover:text-accent-foreground transition-colors min-w-0">
                    <Link
                        href={`/workspaces/${workspaceId}/conversations/${conv.id}`}
                        className={cn(
                        "flex-1 flex items-center gap-2 py-2 pl-3 text-sm font-medium min-w-0 overflow-hidden",
                        isActive ? "text-accent-foreground font-semibold" : "text-muted-foreground"
                        )}
                        title={conv.title || "Untitled Conversation"}
                    >
                        <MessageSquare className="h-4 w-4 shrink-0" />
                        <span className="truncate flex-1 min-w-0">{conv.title || "Untitled Conversation"}</span>
                    </Link>

                    {/* Delete Button */}
                    <Button
                        variant="ghost"
                        size="icon"
                        className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive hover:bg-destructive/10 z-20"
                        onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            setDeleteId(conv.id);
                        }}
                    >
                        <Trash2 className="h-3.5 w-3.5" />
                        <span className="sr-only">Delete</span>
                    </Button>
                  </div>
                );
              })}
            </div>
          </ScrollArea>
      </div>

      {/* Bottom Half: Documents */}
      <div className="flex flex-col h-1/2 min-h-0">
         <DocumentSidebar workspaceId={workspaceId} className="h-full border-l-0 border-t-0 bg-transparent" />
      </div>

      <DeleteConfirmDialog
        open={!!deleteId}
        onOpenChange={(open) => !open && setDeleteId(null)}
        onConfirm={handleDelete}
        title="Delete Conversation?"
        description="This will permanently delete this conversation and all its messages."
        isDeleting={isDeleting}
      />
    </div>
  );
}