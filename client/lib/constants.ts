export const MESSAGE_ROLES = {
  user: "user",
  ai: "ai",
} as const;

export const DOCUMENT_STATUS = {
  pending: "pending",
  parsed: "parsed",
  ingested: "ingested",
  error: "error",
} as const;
