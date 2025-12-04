"use client";

import { ReactQueryProvider } from "@/lib/query-client";
import { type ReactNode } from "react";
import { Toaster } from "sonner";
import { RealtimeProvider } from "@/features/realtime/RealtimeContext";

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ReactQueryProvider>
      <RealtimeProvider>
        {children}
        <Toaster position="top-right" />
      </RealtimeProvider>
    </ReactQueryProvider>
  );
}
