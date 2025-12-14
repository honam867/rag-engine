"use client";

import { useEffect, useRef } from "react";
import { useDocumentRawText, useWorkspaceDocuments } from "../hooks/useDocuments";
import { X, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

interface Props {
  workspaceId: string;
  documentId: string;
  documentTitle?: string;
  highlightSegmentIndex?: number | null;
  onClose: () => void;
}

export function DocumentRawTextViewer({ 
  workspaceId, 
  documentId, 
  documentTitle: initialTitle,
  highlightSegmentIndex, 
  onClose 
}: Props) {
  const { data, isLoading, error } = useDocumentRawText(workspaceId, documentId);
  const { data: documents } = useWorkspaceDocuments(workspaceId);
  
  // Find title if not provided or just "Document"
  const docFromList = documents?.find(d => d.id === documentId);
  const displayTitle = docFromList?.title || initialTitle || "Document Viewer";

  // Auto-scroll when a highlight index is provided (legacy API).
  // Since the raw text is now a single block, we simply scroll to top.
  useEffect(() => {
    if (highlightSegmentIndex !== null && highlightSegmentIndex !== undefined && !isLoading && data) {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, [highlightSegmentIndex, isLoading, data]);

  return (
    <div 
      className="flex flex-col h-full w-full bg-[#FAF9F6] border-l shadow-2xl relative"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-stone-200 bg-[#FAF9F6]/95 backdrop-blur-sm sticky top-0 z-10 shrink-0">
        <div className="flex flex-col min-w-0">
          <span className="text-[10px] font-bold uppercase text-stone-500 tracking-wider">Document Viewer</span>
          <h3 className="text-sm font-semibold truncate text-stone-900" title={displayTitle}>
            {displayTitle}
          </h3>
        </div>
        <Button 
            variant="ghost" 
            size="icon" 
            onClick={onClose} 
            className="shrink-0 ml-2 h-8 w-8 text-stone-500 hover:text-stone-900 hover:bg-stone-200/50"
        >
          <X className="h-4 w-4" />
          <span className="sr-only">Close</span>
        </Button>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 relative">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center h-full text-stone-400 gap-2">
            <Loader2 className="h-6 w-6 animate-spin" />
            <p className="text-sm">Fetching content...</p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full text-red-500 gap-2 p-6 text-center">
            <AlertCircle className="h-6 w-6" />
            <p className="text-sm font-medium">Unable to load document.</p>
          </div>
        ) : (
          <ScrollArea className="h-full w-full">
            <div className="p-8 max-w-3xl mx-auto">
              <div className="space-y-4 text-base leading-relaxed text-stone-800 selection:bg-yellow-200 selection:text-stone-900">
                <p className={cn("whitespace-pre-wrap break-words")}>
                  {data?.text}
                </p>
              </div>
            </div>
          </ScrollArea>
        )}
      </div>
    </div>
  );
}
