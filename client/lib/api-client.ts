"use client";

import { API_BASE_URL } from "./config";
import { supabaseClient } from "./supabase-client";

type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

interface ApiOptions extends RequestInit {
  auth?: boolean;
}

export async function apiFetch<TResponse>(
  path: string,
  { method = "GET", auth = true, headers, body, ...rest }: ApiOptions = {},
): Promise<TResponse> {
  const url = `${API_BASE_URL}${path}`;
  const finalHeaders = new Headers(headers || {});

  if (!(body instanceof FormData)) {
    finalHeaders.set("Content-Type", "application/json");
  }

  if (auth) {
    const {
      data: { session },
    } = await supabaseClient.auth.getSession();
    const token = session?.access_token;
    if (token) {
      finalHeaders.set("Authorization", `Bearer ${token}`);
    }
  }

  const response = await fetch(url, {
    method: method as HttpMethod,
    headers: finalHeaders,
    body,
    ...rest,
  });

  if (!response.ok) {
    let errorBody: unknown = null;
    try {
      errorBody = await response.json();
    } catch {
      // ignore json parse error
    }
    throw new ApiError(response.status, response.statusText, errorBody);
  }

  if (response.status === 204) {
    return null as TResponse;
  }

  return (await response.json()) as TResponse;
}
