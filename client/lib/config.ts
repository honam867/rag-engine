// NOTE: Next.js only inlines env vars when accessed statically.
// Avoid dynamic process.env[key] lookup or they will be undefined on the client.
const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL;
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!apiBase) throw new Error("Missing required env: NEXT_PUBLIC_API_BASE_URL");
if (!supabaseUrl) throw new Error("Missing required env: NEXT_PUBLIC_SUPABASE_URL");
if (!supabaseAnonKey) throw new Error("Missing required env: NEXT_PUBLIC_SUPABASE_ANON_KEY");

export const API_BASE_URL = apiBase;
export const SUPABASE_URL = supabaseUrl;
export const SUPABASE_ANON_KEY = supabaseAnonKey;
