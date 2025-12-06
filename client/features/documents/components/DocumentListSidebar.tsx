"use client";

import { useWorkspaceDocuments } from "../hooks/useDocuments";
import { FileText, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface Props {
  workspaceId: string;
  onDocumentClick?: (documentId: string, title: string) => void;
  className?: string;
}

export function DocumentListSidebar({ workspaceId, onDocumentClick, className }: Props) {
  const { data: documents, isLoading } = useWorkspaceDocuments(workspaceId);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2 p-4">
        {[1, 2, 3].map(i => <div key={i} className="h-8 bg-muted animate-pulse rounded" />)}
      </div>
    );
  }

  if (!documents?.length) {
    return (
      <div className="text-center p-4 text-xs text-muted-foreground">
        No documents found.
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-1 p-2", className)}>
      {documents.map((doc) => (
        <Button
          key={doc.id}
          variant="ghost"
          size="sm"
          className="justify-start h-auto py-2 px-2 text-left font-normal"
          onClick={() => onDocumentClick?.(doc.id, doc.title)}
        >
          <FileText className="h-4 w-4 mr-2 text-muted-foreground shrink-0" />
          <div className="flex flex-col min-w-0 flex-1">
             <span className="truncate text-sm">{doc.title}</span>
             <span className="text-[10px] text-muted-foreground capitalize">{doc.status}</span>
          </div>
        </Button>
      ))}
    </div>
  );
}
