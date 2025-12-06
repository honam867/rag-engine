"use client";

import { useRef, useState } from "react";
import { Plus, FileText, Loader2, CheckCircle, AlertCircle, Clock, ScanText, Upload, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useWorkspaceDocuments, useUploadDocuments, useDeleteDocument } from "../hooks/useDocuments";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { DeleteConfirmDialog } from "@/components/ui/delete-confirm-dialog";
import { useRouter, usePathname, useSearchParams } from "next/navigation";

interface DocumentSidebarProps {
  workspaceId: string;
  className?: string;
}

export function DocumentSidebar({ workspaceId, className }: DocumentSidebarProps) {
  const { data: documents, isLoading } = useWorkspaceDocuments(workspaceId);
  const { mutateAsync: upload, isPending } = useUploadDocuments(workspaceId);
  const { mutateAsync: deleteDocument, isPending: isDeleting } = useDeleteDocument(workspaceId);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const handleDocumentClick = (docId: string) => {
    // Preserve existing params (like initialPrompt if any)
    const params = new URLSearchParams(searchParams.toString());
    params.set("documentId", docId);
    router.replace(`${pathname}?${params.toString()}`);
  };

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

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "ingested":
      case "completed":
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "error":
        return <AlertCircle className="h-4 w-4 text-destructive" />;
      default: 
        return <Loader2 className="h-4 w-4 text-muted-foreground animate-spin" />;
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

          {documents?.map((doc) => {
             const isActive = searchParams.get("documentId") === doc.id;
             return (
             <div 
                key={doc.id} 
                className={cn(
                    "group relative w-full flex items-center justify-between p-2 pr-9 rounded-md transition-colors border cursor-pointer",
                    isActive ? "bg-accent text-accent-foreground border-border" : "hover:bg-accent hover:text-accent-foreground border-transparent hover:border-border"
                )}
                title={`${doc.title} - ${doc.status}`}
                onClick={() => handleDocumentClick(doc.id)}
             >
                <div className="flex items-center gap-2 overflow-hidden w-full min-w-0">
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="text-sm font-medium truncate flex-1">{doc.title}</div>
                </div>
                <div className="shrink-0 pl-1 group-hover:opacity-0 transition-opacity">
                    {getStatusIcon(doc.status)}
                </div>

                {/* Delete Button (Visible on Hover) */}
                <Button
                    variant="ghost"
                    size="icon"
                    className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7 invisible group-hover:visible text-muted-foreground hover:text-destructive hover:bg-destructive/10 z-10"
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
