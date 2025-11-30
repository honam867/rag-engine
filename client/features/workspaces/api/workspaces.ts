import { API_ENDPOINTS } from "@/lib/api-endpoints";
import { apiFetch } from "@/lib/api-client";

export interface Workspace {
  id: string;
  name: string;
  description?: string | null;
  created_at?: string;
}

export interface WorkspaceCreatePayload {
  name: string;
  description?: string | null;
}

export async function fetchWorkspaces(): Promise<Workspace[]> {
  return apiFetch<Workspace[]>(API_ENDPOINTS.workspaces);
}

export async function createWorkspace(payload: WorkspaceCreatePayload): Promise<Workspace> {
  return apiFetch<Workspace>(API_ENDPOINTS.workspaces, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
