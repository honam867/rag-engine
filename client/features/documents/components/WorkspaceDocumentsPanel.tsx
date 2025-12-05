"use client";

import { useRef } from "react";
import { useWorkspaceDocuments, useUploadDocuments } from "../hooks/useDocuments";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { FileText, Upload, CheckCircle, AlertCircle, Clock, ScanText, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface Props {
  workspaceId: string;
}

export function WorkspaceDocumentsPanel({ workspaceId }: Props) {
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
        // Reset input to allow selecting same file again
        if (fileInputRef.current) {
            fileInputRef.current.value = "";
        }
      }
    }
  };

  const getStatusInfo = (status: string) => {
    switch (status) {
      case "ingested":
      case "completed":
        return { icon: CheckCircle, color: "text-green-500", bg: "bg-green-500/10", label: "Ready" };
      case "parsed":
        return { icon: ScanText, color: "text-blue-500", bg: "bg-blue-500/10", label: "Parsed" };
      case "error":
        return { icon: AlertCircle, color: "text-destructive", bg: "bg-destructive/10", label: "Error" };
      default: // pending, running
        return { icon: Clock, color: "text-amber-500", bg: "bg-amber-500/10", label: "Processing" };
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
                    className="group flex items-center justify-between p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors cursor-default"
                    title={`${doc.title} - ${status.label}`}
                >
                    <div className="flex items-center gap-3 min-w-0 overflow-hidden flex-1">
                        <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <span className="text-sm font-medium truncate pr-2">{doc.title}</span>
                    </div>
                    <div className="shrink-0 pl-1">
                        <StatusIcon className={cn("h-3.5 w-3.5", status.color, doc.status === 'pending' && "animate-pulse")} />
                    </div>
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
    </div>
  );
}
