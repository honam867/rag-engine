"use client";

import { useQuery } from "@tanstack/react-query";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchDocuments, uploadDocuments } from "../api/documents";
import { documentKeys } from "@/lib/query-keys";

export function useWorkspaceDocuments(workspaceId: string) {
  return useQuery({
    queryKey: documentKeys.list(workspaceId),
    queryFn: () => fetchDocuments(workspaceId),
    enabled: Boolean(workspaceId),
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
