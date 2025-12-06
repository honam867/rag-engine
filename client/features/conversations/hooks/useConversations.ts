"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createConversation,
  fetchConversations,
  deleteConversation,
  type ConversationCreatePayload,
} from "../api/conversations";
import { conversationKeys } from "@/lib/query-keys";

export function useConversationList(workspaceId: string) {
  return useQuery({
    queryKey: conversationKeys.list(workspaceId),
    queryFn: () => fetchConversations(workspaceId),
    enabled: Boolean(workspaceId),
  });
}

export function useCreateConversation(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ConversationCreatePayload) =>
      createConversation(workspaceId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: conversationKeys.list(workspaceId) });
    },
  });
}

export function useDeleteConversation(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (conversationId: string) => deleteConversation(workspaceId, conversationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: conversationKeys.list(workspaceId) });
    },
  });
}
