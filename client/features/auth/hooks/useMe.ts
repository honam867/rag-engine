"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchMe } from "../api/me";

export function useMe(enabled: boolean) {
  return useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    enabled,
    retry: false,
  });
}
