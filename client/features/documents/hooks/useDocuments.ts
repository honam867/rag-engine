"use client";

import { useQuery } from "@tanstack/react-query";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchDocuments, uploadDocuments, deleteDocument, fetchDocumentRawText } from "../api/documents";
import { documentKeys } from "@/lib/query-keys";

export function useWorkspaceDocuments(workspaceId: string) {
  return useQuery({
    queryKey: documentKeys.list(workspaceId),
    queryFn: () => fetchDocuments(workspaceId),
    enabled: Boolean(workspaceId),
  });
}

export function useDocumentRawText(workspaceId: string, documentId: string | null) {
  return useQuery({
    queryKey: documentKeys.rawText(workspaceId, documentId!),
    queryFn: () => fetchDocumentRawText(workspaceId, documentId!),
    enabled: Boolean(workspaceId) && Boolean(documentId),
    retry: 1, // Don't retry too much on 404/409
  });
}

export function useUploadDocuments(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (files: FileList) => uploadDocuments(workspaceId, files),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: documentKeys.list(workspaceId) });
    },
  });
}

export function useDeleteDocument(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) => deleteDocument(workspaceId, documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: documentKeys.list(workspaceId) });
    },
  });
}
