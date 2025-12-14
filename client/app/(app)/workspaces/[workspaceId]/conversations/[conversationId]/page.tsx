"use client";

import { useRef, useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams, usePathname } from "next/navigation";
import { MessageSquare, ArrowLeft, PanelRight } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatMessageList } from "@/features/messages/components/ChatMessageList";
import { ChatInput } from "@/features/messages/components/ChatInput";
import { useMessageList, useSendMessage } from "@/features/messages/hooks/useMessages";
import { Button } from "@/components/ui/button";
import { Citation } from "@/features/messages/api/messages";
import { ConversationSidebar } from "@/features/conversations/components/ConversationSidebar";
import { DocumentRawTextViewer } from "@/features/documents/components/DocumentRawTextViewer";
import { cn } from "@/lib/utils";

export default function ConversationPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const conversationId = params.conversationId as string;
  const workspaceId = params.workspaceId as string;
  
  const { data: messages, isLoading } = useMessageList(conversationId);
  const sendMessageMutation = useSendMessage(conversationId);
  
  const bottomRef = useRef<HTMLDivElement>(null);
  const hasSentInitialRef = useRef(false);
  const [isRightSidebarOpen, setIsRightSidebarOpen] = useState(true);

  // Viewer Logic
  const documentId = searchParams.get("documentId");
  const segmentParam = searchParams.get("segment");
  const highlightSegment = segmentParam ? parseInt(segmentParam, 10) : null;

  const handleCloseViewer = () => {
    const newParams = new URLSearchParams(searchParams.toString());
    newParams.delete("documentId");
    newParams.delete("segment");
    router.replace(`${pathname}?${newParams.toString()}`);
  };

  // Handle initialPrompt from URL
  useEffect(() => {
    const initialPrompt = searchParams.get("initialPrompt");
    if (initialPrompt && !hasSentInitialRef.current) {
        hasSentInitialRef.current = true;
        const decoded = decodeURIComponent(initialPrompt);
        sendMessageMutation.mutate({ content: decoded });
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

  const handleCitationClick = (citation: Citation) => {
    console.log("👆 Clicked Citation Data:", citation); // Debug log

    const params = new URLSearchParams(searchParams.toString());
    
    if (citation.document_id) {
        params.set("documentId", citation.document_id);
    } else {
        console.warn("⚠️ Citation missing document_id");
        return;
    }

    if (citation.segment_index !== null && citation.segment_index !== undefined) {
        params.set("segment", citation.segment_index.toString());
    } else {
        console.warn("⚠️ Citation missing segment_index (will open doc without scrolling)");
        params.delete("segment");
    }
    
    router.replace(`${pathname}?${params.toString()}`);
  };

  return (
    <div className="flex h-full w-full overflow-hidden bg-background">
      
      {/* 1. Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative z-0">
          {/* Header */}
          <div className="flex items-center h-14 border-b px-4 flex-none shrink-0 bg-background z-10 justify-between">
            <div className="flex items-center gap-2">
                <Button variant="ghost" size="icon" onClick={handleBack} className="-ml-2 text-muted-foreground hover:text-foreground">
                    <ArrowLeft className="h-5 w-5" />
                </Button>
                <span className="font-semibold text-sm">Conversation</span>
            </div>
            <Button 
                variant="ghost" 
                size="icon" 
                onClick={() => setIsRightSidebarOpen(!isRightSidebarOpen)}
                className={cn("text-muted-foreground hover:text-foreground", !isRightSidebarOpen && "bg-muted/10")}
            >
                <PanelRight className="h-5 w-5" />
            </Button>
          </div>

          {/* Messages */}
          <div className="flex-1 min-h-0 relative">
            <ScrollArea className="h-full w-full">
                <div className="px-4 md:px-0 py-6 w-full max-w-3xl mx-auto">
                    {messages && messages.length > 0 ? (
                        <>
                            <ChatMessageList messages={messages} onCitationClick={handleCitationClick} />
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
                            <p className="text-sm text-muted-foreground">Start asking questions about your documents.</p>
                        </div>
                    )}
                </div>
            </ScrollArea>
          </div>

          {/* Input */}
          <div className="flex-none p-4 pb-6 bg-background shrink-0">
            <div className="max-w-3xl mx-auto w-full">
                <ChatInput conversationId={conversationId} />
            </div>
          </div>
      </div>

      {/* 2. Sidebar (Right) */}
      <div 
        className={cn(
            "transition-all duration-300 ease-in-out flex flex-col overflow-hidden",
            isRightSidebarOpen ? "w-[300px] opacity-100" : "w-0 opacity-0"
        )}
      >
        <div className="w-[300px] h-full flex flex-col">
            <ConversationSidebar />
        </div>
      </div>

      {/* 3. Document Viewer (Far Right) */}
      <div 
        className={`
            border-l bg-background transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)] overflow-hidden flex flex-col
            ${documentId ? "w-[0px] lg:w-[500px] xl:w-[600px] opacity-100" : "w-0 opacity-0"}
        `}
      >
        {documentId && (
            <div className="h-full w-[500px] xl:w-[600px] flex flex-col"> 
                <DocumentRawTextViewer 
                    workspaceId={workspaceId}
                    documentId={documentId}
                    documentTitle="Document"
                    highlightSegmentIndex={highlightSegment}
                    onClose={handleCloseViewer}
                />
            </div>
        )}
      </div>
    </div>
  );
}
