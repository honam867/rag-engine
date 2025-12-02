export const API_ENDPOINTS = {
  health: "/health",
  me: "/api/me",
  workspaces: "/api/workspaces",
  workspaceDetail: (workspaceId: string) => `/api/workspaces/${workspaceId}`,
  documents: (workspaceId: string) => `/api/workspaces/${workspaceId}/documents`,
  uploadDocuments: (workspaceId: string) =>
    `/api/workspaces/${workspaceId}/documents/upload`,
  conversations: (workspaceId: string) =>
    `/api/workspaces/${workspaceId}/conversations`,
  messages: (conversationId: string) =>
    `/api/conversations/${conversationId}/messages`,
} as const;
