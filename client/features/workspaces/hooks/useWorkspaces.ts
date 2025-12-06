"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createWorkspace, fetchWorkspaces, deleteWorkspace, type WorkspaceCreatePayload } from "../api/workspaces";
import { workspaceKeys } from "@/lib/query-keys";

export function useWorkspacesList() {
  return useQuery({
    queryKey: workspaceKeys.list(),
    queryFn: fetchWorkspaces,
    select: (data) => {
      // Sort by created_at desc (newest first)
      return [...data].sort((a, b) => {
        if (!a.created_at || !b.created_at) return 0;
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      });
    },
  });
}

export function useCreateWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: WorkspaceCreatePayload) => createWorkspace(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workspaceKeys.list() });
    },
  });
}

export function useDeleteWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (workspaceId: string) => deleteWorkspace(workspaceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workspaceKeys.list() });
    },
  });
}
