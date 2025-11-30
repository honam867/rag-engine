"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createWorkspace, fetchWorkspaces, type WorkspaceCreatePayload } from "../api/workspaces";
import { workspaceKeys } from "@/lib/query-keys";

export function useWorkspacesList() {
  return useQuery({
    queryKey: workspaceKeys.list(),
    queryFn: fetchWorkspaces,
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
