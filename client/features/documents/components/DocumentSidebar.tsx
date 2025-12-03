"use client";

import { useState } from "react";
import { Plus, FileText, Loader2, CheckCircle, AlertCircle, Clock, ScanText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { DocumentUploadZone } from "./DocumentUploadZone";
import { useWorkspaceDocuments } from "../hooks/useDocuments";
import { cn } from "@/lib/utils";

interface DocumentSidebarProps {
  workspaceId: string;
  className?: string;
}

export function DocumentSidebar({ workspaceId, className }: DocumentSidebarProps) {
  const { data: documents, isLoading } = useWorkspaceDocuments(workspaceId);
  const [isUploadOpen, setIsUploadOpen] = useState(false);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "ingested":
      case "completed":
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "parsed":
        return <ScanText className="h-4 w-4 text-blue-500" />;
      case "error":
        return <AlertCircle className="h-4 w-4 text-destructive" />;
      default: // pending
        return <Clock className="h-4 w-4 text-muted-foreground animate-pulse" />;
    }
  };

  return (
    <div className={cn("flex flex-col h-full bg-muted/10 border-l", className)}>
      <div className="flex h-14 items-center justify-between border-b px-4 shrink-0">
        <span className="font-semibold text-sm">Documents</span>
        <Dialog open={isUploadOpen} onOpenChange={setIsUploadOpen}>
          <DialogTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <Plus className="h-4 w-4" />
              <span className="sr-only">Upload</span>
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Upload Documents</DialogTitle>
            </DialogHeader>
            <div className="pt-4">
               <DocumentUploadZone workspaceId={workspaceId} />
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-2 space-y-2">
          {isLoading && (
            <div className="flex items-center justify-center p-4">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          )}

          {!isLoading && documents?.length === 0 && (
             <div className="text-center py-8 px-4 text-xs text-muted-foreground border-dashed border rounded m-2">
                No documents. <br/> Click + to upload.
             </div>
          )}

          {documents?.map((doc) => (
             <div 
                key={doc.id} 
                className="group flex items-center justify-between p-2 rounded-md hover:bg-accent hover:text-accent-foreground transition-colors border border-transparent hover:border-border"
                title={`Status: ${doc.status}`}
             >
                <div className="flex items-center gap-2 overflow-hidden">
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="text-sm font-medium truncate" title={doc.title}>
                        {doc.title}
                    </span>
                </div>
                <div className="shrink-0 pl-2">
                    {getStatusIcon(doc.status)}
                </div>
             </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
