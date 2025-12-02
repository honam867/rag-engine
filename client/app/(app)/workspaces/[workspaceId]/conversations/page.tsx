"use client";

import { ConversationList } from "@/features/conversations/components/ConversationList";
import { CreateConversationForm } from "@/features/conversations/components/CreateConversationForm";
import { useConversationList } from "@/features/conversations/hooks/useConversations";
import { useParams, useRouter } from "next/navigation";
import { ROUTES } from "@/lib/routes";
import { Button } from "@/components/ui/button";
import { ChevronLeft, Loader2 } from "lucide-react";

export default function ConversationsPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params?.workspaceId as string;
  const { data, isLoading, isError } = useConversationList(workspaceId);

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      <div className="flex items-center gap-2 border-b pb-4">
        <Button 
          variant="ghost" 
          size="sm" 
          onClick={() => router.push(ROUTES.workspaceDetail(workspaceId))}
          className="gap-1 pl-0"
        >
          <ChevronLeft className="h-4 w-4" />
          Back to Workspace
        </Button>
      </div>

      <div className="grid gap-8 md:grid-cols-[1fr_300px]">
        <div className="space-y-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Conversations</h1>
            <p className="text-muted-foreground">Resume a past chat or start a new one.</p>
          </div>
          
          {isLoading && (
            <div className="flex justify-center py-8">
               <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          )}
          {isError && (
            <div className="p-4 rounded-md bg-destructive/10 text-destructive text-sm">
              Failed to load conversations.
            </div>
          )}
          {data ? <ConversationList workspaceId={workspaceId} conversations={data} /> : null}
        </div>

        <div>
           <div className="sticky top-8">
              <CreateConversationForm workspaceId={workspaceId} />
           </div>
        </div>
      </div>
    </div>
  );
}
