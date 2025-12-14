"use client";

import { useRef, useState } from "react";
import { useWorkspaceDocuments, useUploadDocuments, useDeleteDocument } from "../hooks/useDocuments";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { FileText, Upload, CheckCircle, AlertCircle, Clock, ScanText, Loader2, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { DeleteConfirmDialog } from "@/components/ui/delete-confirm-dialog";

interface Props {
  workspaceId: string;
  onDocumentClick?: (documentId: string) => void;
}

export function WorkspaceDocumentsPanel({ workspaceId, onDocumentClick }: Props) {
  const { data: documents, isLoading } = useWorkspaceDocuments(workspaceId);
  const { mutateAsync: upload, isPending } = useUploadDocuments(workspaceId);
  const { mutateAsync: deleteDocument, isPending: isDeleting } = useDeleteDocument(workspaceId);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      try {
        await upload(e.target.files);
        toast.success("Started uploading documents");
      } catch (error) {
        toast.error("Failed to upload documents");
      } finally {
        if (fileInputRef.current) {
            fileInputRef.current.value = "";
        }
      }
    }
  };

  const handleDelete = async () => {
    if (!deleteId) return;
    try {
      await deleteDocument(deleteId);
      toast.success("Document deleted");
    } catch (error) {
      toast.error("Failed to delete document");
    } finally {
      setDeleteId(null);
    }
  };

  const getStatusInfo = (status: string) => {
    switch (status) {
      case "ingested":
      case "completed":
        return { icon: CheckCircle, color: "text-green-500", bg: "bg-green-500/10", label: "Ready" };
      case "error":
        return { icon: AlertCircle, color: "text-destructive", bg: "bg-destructive/10", label: "Error" };
      default: // pending, running, parsed
        return { icon: Loader2, color: "text-muted-foreground animate-spin", bg: "bg-muted/10", label: "Processing" };
    }
  };

  if (isLoading) {
    return (
        <div className="w-full grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3 mt-8">
            {[1, 2, 3].map(i => (
                <div key={i} className="h-24 rounded-xl bg-muted animate-pulse" />
            ))}
        </div>
    );
  }

  return (
    <div className="w-full max-w-2xl mt-8 pb-20">
      <h3 className="text-sm font-medium text-muted-foreground mb-3 px-1">Documents</h3>
      
      {/* Document Grid */}
      <div className="grid gap-2 grid-cols-1 md:grid-cols-2 lg:grid-cols-3 mb-4">
        {documents?.map((doc) => {
            const status = getStatusInfo(doc.status);
            const StatusIcon = status.icon;
            
            return (
                <div 
                    key={doc.id} 
                    className="group relative flex items-center justify-between p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors cursor-pointer"
                    title={`${doc.title} - ${status.label}`}
                    onClick={() => onDocumentClick?.(doc.id)}
                >
                    <div className="flex items-center gap-3 min-w-0 overflow-hidden flex-1">
                        <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <span className="text-sm font-medium truncate pr-2">{doc.title}</span>
                    </div>
                    <div className="shrink-0 pl-1 group-hover:opacity-0 transition-opacity">
                        <StatusIcon className={cn("h-3.5 w-3.5", status.color, doc.status === 'pending' && "animate-pulse")} />
                    </div>
                    
                    {/* Delete Button (Visible on Hover) */}
                    <Button
                        variant="ghost"
                        size="icon"
                        className="absolute right-1 h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                        onClick={(e) => {
                            e.stopPropagation();
                            setDeleteId(doc.id);
                        }}
                    >
                        <Trash2 className="h-3.5 w-3.5" />
                        <span className="sr-only">Delete</span>
                    </Button>
                </div>
            );
        })}
      </div>

      {/* Upload Button - Full Width */}
      <Card 
          className="border-dashed border-2 hover:border-primary/50 hover:bg-primary/5 transition-colors cursor-pointer flex items-center justify-center py-4 shadow-none bg-transparent"
          onClick={() => !isPending && fileInputRef.current?.click()}
      >
          <input 
              type="file" 
              multiple 
              className="hidden" 
              ref={fileInputRef}
              onChange={handleFileSelect}
              disabled={isPending}
          />
          <div className="flex items-center gap-2 text-muted-foreground">
              {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
              <span className="font-medium text-sm">{isPending ? "Uploading..." : "Upload New Documents"}</span>
          </div>
      </Card>

      <DeleteConfirmDialog
        open={!!deleteId}
        onOpenChange={(open) => !open && setDeleteId(null)}
        onConfirm={handleDelete}
        title="Delete Document?"
        description="This will permanently delete the document and its index. Chat responses referencing this document may become less accurate."
        isDeleting={isDeleting}
      />
    </div>
  );
}
