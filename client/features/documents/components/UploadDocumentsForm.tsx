"use client";

import { useState } from "react";
import { useUploadDocuments } from "../hooks/useDocuments";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loader2, Upload } from "lucide-react";

interface Props {
  workspaceId: string;
}

export function UploadDocumentsForm({ workspaceId }: Props) {
  const { mutateAsync, isPending } = useUploadDocuments(workspaceId);
  const [files, setFiles] = useState<FileList | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!files || files.length === 0) {
      setError("Please select at least one file.");
      return;
    }
    setError(null);
    try {
      await mutateAsync(files);
      setFiles(null);
      // Reset input if possible or rely on key change, but basic reset is fine for now
      const fileInput = document.getElementById("file-upload") as HTMLInputElement;
      if (fileInput) fileInput.value = "";
    } catch (err) {
      setError("Upload failed. Check R2 config or server logs.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upload Documents</CardTitle>
        <CardDescription>Upload PDF, TXT, or MD files to index them.</CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit}>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Input
              id="file-upload"
              type="file"
              multiple
              onChange={(e) => setFiles(e.target.files)}
              className="cursor-pointer"
              disabled={isPending}
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </CardContent>
        <CardFooter>
          <Button type="submit" disabled={isPending || !files}>
            {isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
            {isPending ? "Uploading..." : "Upload"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
