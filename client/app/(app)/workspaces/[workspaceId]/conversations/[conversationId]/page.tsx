"use client";

import { ChatInput } from "@/features/messages/components/ChatInput";
import { ChatMessageList } from "@/features/messages/components/ChatMessageList";
import { useMessageList } from "@/features/messages/hooks/useMessages";
import { useParams, useRouter } from "next/navigation";
import { ROUTES } from "@/lib/routes";
import { Button } from "@/components/ui/button";
import { ChevronLeft } from "lucide-react";
import { Loader2 } from "lucide-react";

export default function ConversationDetailPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params?.workspaceId as string;
  const conversationId = params?.conversationId as string;
  const { data, isLoading, isError } = useMessageList(conversationId);

  return (
    <div className="flex flex-col gap-6 h-full max-w-4xl mx-auto">
      <div className="flex items-center gap-2 border-b pb-4">
        <Button 
          variant="ghost" 
          size="sm" 
          onClick={() => router.push(ROUTES.workspaceConversations(workspaceId))}
          className="gap-1 pl-0"
        >
          <ChevronLeft className="h-4 w-4" />
          Back
        </Button>
        <div>
          <h1 className="text-lg font-semibold">Conversation</h1>
        </div>
      </div>

      <div className="flex-1 min-h-[50vh]">
        {isLoading && (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        )}
        {isError && (
          <div className="p-4 rounded-md bg-destructive/10 text-destructive text-sm">
            Failed to load messages. Please try again.
          </div>
        )}
        {data ? <ChatMessageList messages={data} /> : null}
      </div>

      <div className="sticky bottom-0 bg-background pt-4 pb-2">
        <ChatInput conversationId={conversationId} />
      </div>
    </div>
  );
}
