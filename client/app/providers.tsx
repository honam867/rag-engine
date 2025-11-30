"use client";

import { ReactQueryProvider } from "@/lib/query-client";
import { type ReactNode } from "react";

export function AppProviders({ children }: { children: ReactNode }) {
  return <ReactQueryProvider>{children}</ReactQueryProvider>;
}
