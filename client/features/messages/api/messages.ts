import { API_ENDPOINTS } from "@/lib/api-endpoints";
import { apiFetch } from "@/lib/api-client";

export interface Citation {
  document_id: string;
  segment_index: number;
  page_idx?: number;
  snippet_preview?: string;
}

export interface MessageSection {
  text: string;
  citations: Citation[];
  source_ids?: string[]; // Phase 7.2: List of raw segment IDs from LLM
}

export interface MessageMetadata {
  sections?: MessageSection[];
  citations?: Citation[];
  [key: string]: unknown;
}

export interface Message {
  id: string;
  conversation_id?: string;
  role: string;
  content: string;
  status?: string;
  metadata?: MessageMetadata | null;
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
