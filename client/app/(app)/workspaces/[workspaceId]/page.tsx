"use client";

import { useState } from "react";
import { useParams, useRouter, useSearchParams, usePathname } from "next/navigation";
import { Send, Sparkles, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";

import { useWorkspaceDocuments } from "@/features/documents/hooks/useDocuments";
import { useCreateConversation } from "@/features/conversations/hooks/useConversations";
import { RecentConversations } from "@/features/conversations/components/RecentConversations";
import { WorkspaceDocumentsPanel } from "@/features/documents/components/WorkspaceDocumentsPanel";
import { DocumentRawTextViewer } from "@/features/documents/components/DocumentRawTextViewer";

export default function WorkspaceDashboardPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const workspaceId = params.workspaceId as string;
  const router = useRouter();
  
  const [input, setInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { data: documents, isLoading: isLoadingDocs } = useWorkspaceDocuments(workspaceId);
  const createConvMutation = useCreateConversation(workspaceId);

  // Viewer Logic
  const documentId = searchParams.get("documentId");
  
  const handleDocumentClick = (docId: string) => {
    const newParams = new URLSearchParams(searchParams.toString());
    newParams.set("documentId", docId);
    router.replace(`${pathname}?${newParams.toString()}`);
  };

  const handleCloseViewer = () => {
    const newParams = new URLSearchParams(searchParams.toString());
    newParams.delete("documentId");
    router.replace(`${pathname}?${newParams.toString()}`);
  };

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
      const targetUrl = `/workspaces/${workspaceId}/conversations/${conversation.id}?initialPrompt=${encodedPrompt}`;
      router.push(targetUrl);
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
    <div className="flex h-full w-full bg-background overflow-hidden">
        {/* Main Content Area - Full Width */}
        <div className="flex-1 flex flex-col h-full overflow-hidden relative">
            <ScrollArea className="h-full">
                <div className="flex flex-col items-center justify-start min-h-full p-8 pb-20 max-w-4xl mx-auto w-full space-y-12 pt-[8vh]">
                    
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
                            placeholder={hasDocuments ? "Ask a question..." : "Upload documents to start..."}
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
                                <span>Please upload documents below to start.</span>
                            </div>
                        )}
                    </div>

                    {/* 2. Recent Conversations */}
                    <RecentConversations workspaceId={workspaceId} />

                    {/* 3. Documents Panel (New) */}
                    <WorkspaceDocumentsPanel 
                        workspaceId={workspaceId} 
                        onDocumentClick={handleDocumentClick}
                    />

                </div>
            </ScrollArea>
        </div>

        {/* 4. Document Viewer (Right Panel) */}
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
                        onClose={handleCloseViewer}
                    />
                </div>
            )}
        </div>
    </div>
  );
}