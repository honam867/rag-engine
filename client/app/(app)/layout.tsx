"use client";

import { AppShell } from "@/components/layout/AppShell";
import { ROUTES } from "@/lib/routes";
import { useSupabaseSession } from "@/features/auth/hooks/useSupabaseSession";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect } from "react";
import { useMe } from "@/features/auth/hooks/useMe";
import { supabaseClient } from "@/lib/supabase-client";

export default function AppLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { token, loading } = useSupabaseSession();
  const { data: me, isLoading: loadingMe, isError } = useMe(Boolean(token));

  useEffect(() => {
    if (!loading && !token) {
      router.replace(ROUTES.login);
    }
  }, [loading, token, router]);

  useEffect(() => {
    const handleAuthError = async () => {
      if (isError) {
        await supabaseClient.auth.signOut();
        router.replace(ROUTES.login);
      }
    };
    handleAuthError();
  }, [isError, router]);

  if (loading || !token || loadingMe) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-foreground">
        <div className="text-sm text-gray-600">Checking session...</div>
      </div>
    );
  }

  return <AppShell userEmail={me?.email ?? null} onSignOut={async () => {
    await supabaseClient.auth.signOut();
    router.replace(ROUTES.login);
  }}>{children}</AppShell>;
}
