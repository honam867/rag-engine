"use client";

import { useRef } from "react";
import { Plus, FileText, Loader2, CheckCircle, AlertCircle, Clock, ScanText, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useWorkspaceDocuments, useUploadDocuments } from "../hooks/useDocuments";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface DocumentSidebarProps {
  workspaceId: string;
  className?: string;
}

export function DocumentSidebar({ workspaceId, className }: DocumentSidebarProps) {
  const { data: documents, isLoading } = useWorkspaceDocuments(workspaceId);
  const { mutateAsync: upload, isPending } = useUploadDocuments(workspaceId);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      try {
        await upload(e.target.files);
        toast.success("Started uploading documents");
      } catch (error) {
        toast.error("Failed to upload documents");
      } finally {
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    }
  };

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
      </div>

      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {isLoading && (
            <div className="flex items-center justify-center p-4">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          )}

          {!isLoading && documents?.length === 0 && (
             <div className="text-center py-4 px-4 text-xs text-muted-foreground">
                No documents yet.
             </div>
          )}

          {documents?.map((doc) => (
             <div 
                key={doc.id} 
                className="group flex items-center justify-between p-2 rounded-md hover:bg-accent hover:text-accent-foreground transition-colors border border-transparent hover:border-border cursor-default"
                title={`${doc.title} - ${doc.status}`}
             >
                <div className="flex items-center gap-2 overflow-hidden w-full min-w-0">
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="text-sm font-medium truncate pr-2 flex-1">{doc.title}</span>
                </div>
                <div className="shrink-0 pl-1">
                    {getStatusIcon(doc.status)}
                </div>
             </div>
          ))}

          {/* Upload Button as List Item */}
          <div className="pt-2">
            <input 
                type="file" 
                multiple 
                className="hidden" 
                ref={fileInputRef}
                onChange={handleFileSelect}
                disabled={isPending}
            />
            <Button 
                variant="outline" 
                className="w-full gap-2 border-dashed bg-background text-muted-foreground hover:text-foreground h-9" 
                onClick={() => fileInputRef.current?.click()}
                disabled={isPending}
            >
                {isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Upload className="h-3 w-3" />}
                <span className="text-xs">Upload New Document</span>
            </Button>
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}
