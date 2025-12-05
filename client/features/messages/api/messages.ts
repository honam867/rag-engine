import { API_ENDPOINTS } from "@/lib/api-endpoints";
import { apiFetch } from "@/lib/api-client";

export interface Message {
  id: string;
  conversation_id?: string; // Optional because API might not always return it in list, but used in websocket/optimistic
  role: string;
  content: string;
  status?: string; // 'pending' | 'running' | 'done' | 'error'
  metadata?: Record<string, unknown> | null;
  created_at?: string;
  isOptimistic?: boolean;
}

export interface MessageListResponse {
  items: Message[];
}

export interface MessageCreatePayload {
  content: string;
}

export async function fetchMessages(conversationId: string): Promise<Message[]> {
  const res = await apiFetch<MessageListResponse>(API_ENDPOINTS.messages(conversationId));
  return res.items;
}

export async function sendMessage(
  conversationId: string,
  payload: MessageCreatePayload,
): Promise<Message> {
  return apiFetch<Message>(API_ENDPOINTS.messages(conversationId), {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
