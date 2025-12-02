import { API_ENDPOINTS } from "@/lib/api-endpoints";
import { apiFetch } from "@/lib/api-client";

export interface Message {
  id: string;
  role: string;
  content: string;
  metadata?: Record<string, unknown> | null;
  created_at?: string;
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
