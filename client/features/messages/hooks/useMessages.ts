"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchMessages, sendMessage, type MessageCreatePayload } from "../api/messages";
import { conversationKeys } from "@/lib/query-keys";

export function useMessageList(conversationId: string) {
  return useQuery({
    queryKey: conversationKeys.messages(conversationId),
    queryFn: () => fetchMessages(conversationId),
    enabled: Boolean(conversationId),
  });
}

export function useSendMessage(conversationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: MessageCreatePayload) => sendMessage(conversationId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: conversationKeys.messages(conversationId) });
    },
  });
}
