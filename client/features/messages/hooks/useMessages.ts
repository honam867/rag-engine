"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchMessages, sendMessage, type MessageCreatePayload, type Message } from "../api/messages";
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
    onMutate: async (newMsgPayload) => {
      // 1. Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: conversationKeys.messages(conversationId) });

      // 2. Snapshot previous data
      const previousMessages = queryClient.getQueryData(conversationKeys.messages(conversationId));

      // 3. Create optimistic messages
      const tempUserMsgId = crypto.randomUUID();
      const tempAiMsgId = crypto.randomUUID();
      
      const optimisticUserMsg: Message = {
        id: tempUserMsgId,
        conversation_id: conversationId,
        role: "user",
        content: newMsgPayload.content,
        status: "done", // User message is implicitly done
        created_at: new Date().toISOString(),
      };

      const optimisticAiMsg: Message = {
        id: tempAiMsgId,
        conversation_id: conversationId,
        role: "ai",
        content: "", // Empty or "Thinking..."
        status: "pending", // Important for showing spinner
        created_at: new Date().toISOString(),
      };

      // 4. Update cache
      queryClient.setQueryData(conversationKeys.messages(conversationId), (old: any) => {
          const items = Array.isArray(old) ? old : old?.items || [];
          // Adjust structure based on your actual API return (if it returns { items: [...] } or just [...])
          const newItems = [...items, optimisticUserMsg, optimisticAiMsg];
          return Array.isArray(old) ? newItems : { ...old, items: newItems };
      });

      return { previousMessages };
    },
    onError: (err, newTodo, context) => {
      // Rollback
      if (context?.previousMessages) {
        queryClient.setQueryData(conversationKeys.messages(conversationId), context.previousMessages);
      }
    },
    onSettled: () => {
      // With WebSocket, we might not strictly need to invalidate, 
      // but it's good practice to ensure consistency eventually.
      // queryClient.invalidateQueries({ queryKey: conversationKeys.messages(conversationId) });
    },
  });
}
