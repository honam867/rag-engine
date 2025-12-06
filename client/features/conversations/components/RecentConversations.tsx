"use client";

import { useState } from "react";
import { useConversationList, useDeleteConversation } from "@/features/conversations/hooks/useConversations";
import Link from "next/link";
import { MessageSquare, Clock, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { DeleteConfirmDialog } from "@/components/ui/delete-confirm-dialog";
import { toast } from "sonner";

export function RecentConversations({ workspaceId }: { workspaceId: string }) {
  const { data: conversations, isLoading } = useConversationList(workspaceId);
  const { mutateAsync: deleteConversation, isPending: isDeleting } = useDeleteConversation(workspaceId);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  const handleDelete = async () => {
    if (!deleteId) return;
    try {
      await deleteConversation(deleteId);
      toast.success("Conversation deleted");
    } catch (error) {
      toast.error("Failed to delete conversation");
    } finally {
      setDeleteId(null);
    }
  };

  if (isLoading) {
      return <div className="h-12 w-full bg-muted rounded animate-pulse" />;
  }

  if (!conversations || conversations.length === 0) return null;

  const displayedConversations = showAll ? conversations : conversations.slice(0, 3);

  return (
    <div className="w-full max-w-2xl mt-8">
        <h3 className="text-sm font-medium text-muted-foreground mb-3 px-1">Recent Conversations</h3>
        <div className="grid gap-2">
            {displayedConversations.map((conv) => (
                <div key={conv.id} className="group relative flex items-center">
                    <Link
                        href={`/workspaces/${workspaceId}/conversations/${conv.id}`}
                        className={cn(
                            "flex-1 flex items-center gap-3 p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors cursor-pointer min-w-0"
                        )}
                    >
                        <div className="p-2 rounded bg-primary/10 text-primary shrink-0">
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

                    {/* Delete Button */}
                    <Button
                        variant="ghost"
                        size="icon"
                        className="absolute right-2 h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                        onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            setDeleteId(conv.id);
                        }}
                    >
                        <Trash2 className="h-4 w-4" />
                        <span className="sr-only">Delete</span>
                    </Button>
                </div>
            ))}
        </div>
        {conversations.length > 3 && (
            <div className="mt-2 text-center">
                <Button 
                    variant="link" 
                    size="sm" 
                    className="text-xs text-muted-foreground h-auto p-0"
                    onClick={() => setShowAll(!showAll)}
                >
                    {showAll ? "Show less" : "View more history"}
                </Button>
            </div>
        )}

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
