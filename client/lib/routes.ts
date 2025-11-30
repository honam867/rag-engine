export const ROUTES = {
  login: "/login",
  appRoot: "/workspaces",
  workspaces: "/workspaces",
  workspaceDetail: (workspaceId: string) => `/workspaces/${workspaceId}`,
  workspaceConversations: (workspaceId: string) =>
    `/workspaces/${workspaceId}/conversations`,
  conversationDetail: (workspaceId: string, conversationId: string) =>
    `/workspaces/${workspaceId}/conversations/${conversationId}`,
} as const;
