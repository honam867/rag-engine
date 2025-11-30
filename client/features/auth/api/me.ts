import { API_ENDPOINTS } from "@/lib/api-endpoints";
import { apiFetch } from "@/lib/api-client";

export interface CurrentUser {
  id: string;
  email?: string | null;
}

export async function fetchMe(): Promise<CurrentUser> {
  return apiFetch<CurrentUser>(API_ENDPOINTS.me);
}
