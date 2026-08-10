// Blocco 1 (migrazione Emergent -> Supabase/Render) — client Supabase Auth per
// l'app mobile. Sostituisce il flusso OAuth custom verso auth.emergentagent.com
// (vedi src/context/AuthContext.tsx) con l'auth nativa di Supabase, la stessa
// già usata da jobby-web.
//
// Pattern standard Supabase+Expo: AsyncStorage come storage adapter su nativo
// (persistenza sessione tra riavvii app), storage di default (browser) su web.
import "react-native-url-polyfill/auto";
import { createClient } from "@supabase/supabase-js";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Platform } from "react-native";

const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL as string;
const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY as string;

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  // Fallisce rumorosamente in dev invece di lasciare che le chiamate auth
  // falliscano più avanti con un errore criptico.
  console.warn(
    "[supabase] EXPO_PUBLIC_SUPABASE_URL / EXPO_PUBLIC_SUPABASE_ANON_KEY mancanti — impostale in frontend/.env"
  );
}

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    storage: Platform.OS === "web" ? undefined : AsyncStorage,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: Platform.OS === "web",
  },
});
