"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Send, Sparkles, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";

import { useWorkspaceDocuments } from "@/features/documents/hooks/useDocuments";
import { useCreateConversation } from "@/features/conversations/hooks/useConversations";
import { RecentConversations } from "@/features/conversations/components/RecentConversations";
import { DocumentSidebar } from "@/features/documents/components/DocumentSidebar";

export default function WorkspaceDashboardPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const router = useRouter();
  
  const [input, setInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { data: documents, isLoading: isLoadingDocs } = useWorkspaceDocuments(workspaceId);
  const createConvMutation = useCreateConversation(workspaceId);

  const hasDocuments = documents && documents.length > 0;

  const handleSend = async () => {
    if (!input.trim() || isSubmitting) return;
    
    setIsSubmitting(true);
    try {
      // 1. Create Conversation
      const title = input.trim().substring(0, 50) + (input.length > 50 ? "..." : "");
      const conversation = await createConvMutation.mutateAsync({ title });
      
      // 2. Navigate immediately with initial prompt
      // We encode it to safely pass via URL
      const encodedPrompt = encodeURIComponent(input.trim());
      router.push(`/workspaces/${workspaceId}/conversations/${conversation.id}?initialPrompt=${encodedPrompt}`);
    } catch (error) {
      console.error("Failed to start conversation:", error);
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex h-full max-h-full bg-background overflow-hidden">
        {/* Main Content Area (Left) */}
        <div className="flex-1 flex flex-col h-full overflow-hidden relative">
            <ScrollArea className="h-full">
                <div className="flex flex-col items-center justify-start min-h-full p-8 pb-20 max-w-4xl mx-auto w-full space-y-12 pt-[10vh]">
                    
                    {/* 1. Main Input Section */}
                    <div className="w-full max-w-2xl space-y-6 text-center">
                        <div className="space-y-2">
                            <h1 className="text-3xl font-semibold tracking-tight">
                            What would you like to know?
                            </h1>
                            <p className="text-lg text-muted-foreground">
                            Ask questions about your documents.
                            </p>
                        </div>

                        <div className="relative text-left shadow-lg rounded-xl">
                            <Textarea
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder={hasDocuments ? "Ask a question..." : "Upload documents in the sidebar to start..."}
                            className="min-h-[120px] resize-none pr-12 text-lg p-6 rounded-xl border-muted-foreground/20 focus-visible:ring-primary/30"
                            disabled={!hasDocuments || isSubmitting || isLoadingDocs}
                            />
                            <Button
                            size="icon"
                            className="absolute bottom-4 right-4 h-10 w-10 rounded-full shadow-sm"
                            disabled={!input.trim() || !hasDocuments || isSubmitting}
                            onClick={handleSend}
                            >
                            {isSubmitting ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
                            </Button>
                        </div>

                        {!hasDocuments && !isLoadingDocs && (
                            <div className="flex items-center gap-2 justify-center text-sm text-amber-600 bg-amber-50 p-3 rounded-lg border border-amber-100">
                                <Sparkles className="h-4 w-4" />
                                <span>Please upload documents using the sidebar on the right.</span>
                            </div>
                        )}
                    </div>

                    {/* 2. Recent Conversations */}
                    <RecentConversations workspaceId={workspaceId} />

                </div>
            </ScrollArea>
        </div>

        {/* Right Sidebar: Documents */}
        <DocumentSidebar workspaceId={workspaceId} className="w-[300px] hidden md:flex border-l bg-muted/10" />
    </div>
  );
}