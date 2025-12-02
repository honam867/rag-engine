import { API_ENDPOINTS } from "@/lib/api-endpoints";
import { apiFetch } from "@/lib/api-client";

export interface Conversation {
  id: string;
  workspace_id: string;
  title: string;
  created_at?: string;
}

export interface ConversationListResponse {
  items: Conversation[];
}

export interface ConversationCreatePayload {
  title: string;
}

export async function fetchConversations(workspaceId: string): Promise<Conversation[]> {
  const res = await apiFetch<ConversationListResponse>(API_ENDPOINTS.conversations(workspaceId));
  return res.items;
}

export async function createConversation(
  workspaceId: string,
  payload: ConversationCreatePayload,
): Promise<Conversation> {
  return apiFetch<Conversation>(API_ENDPOINTS.conversations(workspaceId), {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
