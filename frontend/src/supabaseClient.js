import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || "https://bidulflwmmxiwllcpyvr.supabase.co";
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJpZHVsZmx3bW14aXdsbGNweXZyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkwNDUxMDcsImV4cCI6MjA4NDYyMTEwN30.6u5I8hiqCYSoX6eTBHWxrleU4Km-mp5XbbuuvvSddbM";

if (!import.meta.env.VITE_SUPABASE_URL || !import.meta.env.VITE_SUPABASE_ANON_KEY) {
  console.warn("[Supabase] Environment variables not set. Using fallback values.");
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
