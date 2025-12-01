"use client";

import { useState, useCallback } from "react";
import { useUploadDocuments } from "../hooks/useDocuments";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2, Upload, File as FileIcon, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  workspaceId: string;
}

export function DocumentUploadZone({ workspaceId }: Props) {
  const { mutateAsync, isPending } = useUploadDocuments(workspaceId);
  const [isDragging, setIsDragging] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const onDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const newFiles = Array.from(e.dataTransfer.files);
      setFiles((prev) => [...prev, ...newFiles]);
      setError(null);
    }
  }, []);

  const onFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
        const newFiles = Array.from(e.target.files);
        setFiles((prev) => [...prev, ...newFiles]);
        setError(null);
    }
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleUpload = async () => {
    if (files.length === 0) return;
    
    // Convert File[] to FileList-like object for API
    const dataTransfer = new DataTransfer();
    files.forEach(file => dataTransfer.items.add(file));
    
    try {
      await mutateAsync(dataTransfer.files);
      setFiles([]);
    } catch (err) {
      setError("Upload failed.");
    }
  };

  return (
    <div className="space-y-4">
        {/* Drop Zone */}
        <div
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            className={cn(
                "border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer",
                isDragging ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-primary/50",
                "flex flex-col items-center justify-center gap-2"
            )}
            onClick={() => document.getElementById("hidden-file-input")?.click()}
        >
            <input 
                id="hidden-file-input" 
                type="file" 
                multiple 
                className="hidden" 
                onChange={onFileSelect} 
                disabled={isPending}
            />
            <div className="p-3 bg-muted rounded-full">
                <Upload className="h-6 w-6 text-muted-foreground" />
            </div>
            <div className="text-sm font-medium">
                Click to upload or drag and drop
            </div>
            <p className="text-xs text-muted-foreground">
                PDF, TXT, MD (max 10MB)
            </p>
        </div>

        {/* Selected Files Preview */}
        {files.length > 0 && (
            <div className="space-y-2">
                <div className="text-sm font-medium text-muted-foreground">Selected files:</div>
                <div className="space-y-2 max-h-[150px] overflow-y-auto pr-2">
                    {files.map((file, idx) => (
                        <div key={idx} className="flex items-center justify-between p-2 bg-muted/30 rounded border text-sm">
                            <div className="flex items-center gap-2 truncate">
                                <FileIcon className="h-4 w-4 text-blue-500 shrink-0" />
                                <span className="truncate max-w-[200px]">{file.name}</span>
                            </div>
                            <Button 
                                variant="ghost" 
                                size="icon" 
                                className="h-6 w-6" 
                                onClick={() => removeFile(idx)}
                                disabled={isPending}
                            >
                                <X className="h-3 w-3" />
                            </Button>
                        </div>
                    ))}
                </div>
                <Button 
                    className="w-full" 
                    onClick={handleUpload} 
                    disabled={isPending}
                >
                    {isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    Upload {files.length} file{files.length > 1 ? 's' : ''}
                </Button>
            </div>
        )}

        {error && <p className="text-sm text-destructive text-center">{error}</p>}
    </div>
  );
}
