"use client";

import { supabaseClient } from "@/lib/supabase-client";
import { useEffect, useState } from "react";

export function useSupabaseSession() {
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    const getSession = async () => {
      const {
        data: { session },
      } = await supabaseClient.auth.getSession();
      if (!mounted) return;
      setToken(session?.access_token ?? null);
      setLoading(false);
    };
    getSession();
    const { data: subscription } = supabaseClient.auth.onAuthStateChange((_event, session) => {
      if (!mounted) return;
      setToken(session?.access_token ?? null);
    });
    return () => {
      mounted = false;
      subscription.subscription.unsubscribe();
    };
  }, []);

  return { token, loading };
}
