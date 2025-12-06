export const workspaceKeys = {
  all: ["workspaces"] as const,
  list: () => [...workspaceKeys.all, "list"] as const,
  detail: (id: string) => [...workspaceKeys.all, "detail", id] as const,
};

export const documentKeys = {
  list: (workspaceId: string) => ["documents", "list", workspaceId] as const,
  rawText: (workspaceId: string, documentId: string) => ["documents", "rawText", workspaceId, documentId] as const,
};

export const conversationKeys = {
  list: (workspaceId: string) => ["conversations", "list", workspaceId] as const,
  messages: (conversationId: string) => ["messages", "list", conversationId] as const,
};
