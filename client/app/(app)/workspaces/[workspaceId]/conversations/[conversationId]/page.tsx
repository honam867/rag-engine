"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { MessageSquare, ArrowLeft } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatMessageList } from "@/features/messages/components/ChatMessageList";
import { ChatInput } from "@/features/messages/components/ChatInput";
import { useMessageList, useSendMessage } from "@/features/messages/hooks/useMessages";
import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";

export default function ConversationPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const conversationId = params.conversationId as string;
  const workspaceId = params.workspaceId as string;
  
  const { data: messages, isLoading } = useMessageList(conversationId);
  const sendMessageMutation = useSendMessage(conversationId);
  
  const bottomRef = useRef<HTMLDivElement>(null);
  const hasSentInitialRef = useRef(false);
  
  // Handle initialPrompt from URL (e.g. from Workspace Dashboard)
  useEffect(() => {
    const initialPrompt = searchParams.get("initialPrompt");
    
    // Only trigger if we have a prompt AND the message list query has initialized (even if loading)
    // This ensures cancelQueries in mutation works correctly against the active query.
    if (initialPrompt && !hasSentInitialRef.current) {
        hasSentInitialRef.current = true;
        const decoded = decodeURIComponent(initialPrompt);
        
        // Send message (Optimistic UI will show it immediately)
        sendMessageMutation.mutate({ content: decoded });
        
        // Use window.history.replaceState to clean URL without triggering a router navigation/remount
        const newUrl = window.location.pathname;
        window.history.replaceState({}, '', newUrl);
    }
  }, [searchParams, sendMessageMutation]);

  // Auto-scroll to bottom
  useEffect(() => {
     if (messages?.length) {
         bottomRef.current?.scrollIntoView({ behavior: "smooth" });
     }
  }, [messages]);

  const handleBack = () => {
    router.push(`/workspaces/${workspaceId}`);
  };

  return (
    <div className="flex flex-col h-screen max-h-screen bg-background overflow-hidden relative">
      {/* Header */}
      <div className="flex items-center h-14 border-b px-4 flex-none shrink-0 bg-background z-10 justify-between">
        <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" onClick={handleBack} className="-ml-2 text-muted-foreground hover:text-foreground">
                <ArrowLeft className="h-5 w-5" />
            </Button>
            <span className="font-semibold text-sm">Conversation</span>
        </div>
        {/* Optional: Add conversation settings/details button here */}
      </div>

      {/* Messages Container */}
      <div className="flex-1 min-h-0 relative">
          <ScrollArea className="h-full w-full">
             <div className="px-4 md:px-0 py-6 w-full max-w-3xl mx-auto">
                {/* 
                   Prioritize showing messages if we have any (from cache/optimistic).
                   Only show loading skeleton if we have NO messages AND are loading.
                */}
                {messages && messages.length > 0 ? (
                    <>
                        <ChatMessageList messages={messages} />
                        <div ref={bottomRef} className="h-4" />
                    </>
                ) : isLoading ? (
                    <div className="space-y-6 px-4">
                        {[1, 2, 3].map(i => (
                            <div key={i} className="flex gap-4 items-start">
                                <div className="h-8 w-8 rounded-full bg-muted animate-pulse shrink-0" />
                                <div className="space-y-2 flex-1">
                                    <div className="h-4 w-3/4 bg-muted rounded animate-pulse" />
                                    <div className="h-4 w-1/2 bg-muted rounded animate-pulse" />
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center p-8 text-center h-64">
                        <MessageSquare className="h-12 w-12 text-muted-foreground mb-4" />
                        <p className="text-sm text-muted-foreground">Start a conversation to ask questions about your documents.</p>
                    </div>
                )}
             </div>
          </ScrollArea>
      </div>

      {/* Input Area */}
      <div className="flex-none p-4 pb-6 bg-background shrink-0">
         <div className="max-w-3xl mx-auto w-full">
            <ChatInput conversationId={conversationId} />
         </div>
      </div>
    </div>
  );
}