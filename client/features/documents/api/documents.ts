import { API_ENDPOINTS } from "@/lib/api-endpoints";
import { apiFetch } from "@/lib/api-client";

export interface Document {
  id: string;
  title: string;
  status: string;
  created_at?: string;
}

export interface DocumentListResponse {
  items: Document[];
}

export async function fetchDocuments(workspaceId: string): Promise<Document[]> {
  const res = await apiFetch<DocumentListResponse>(API_ENDPOINTS.documents(workspaceId));
  return res.items;
}

export async function uploadDocuments(workspaceId: string, files: FileList): Promise<void> {
  const form = new FormData();
  Array.from(files).forEach((file) => {
    form.append("files", file, file.name);
  });
  await apiFetch(API_ENDPOINTS.uploadDocuments(workspaceId), {
    method: "POST",
    body: form,
  });
}

export async function deleteDocument(workspaceId: string, documentId: string): Promise<void> {
  // Assuming standard REST: /api/workspaces/{wid}/documents/{did}
  // API_ENDPOINTS.documents(wid) returns /api/workspaces/{wid}/documents
  const url = `${API_ENDPOINTS.documents(workspaceId)}/${documentId}`;
  await apiFetch(url, {
    method: "DELETE",
  });
}
