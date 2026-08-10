// Blocco 1 (migrazione Emergent -> Supabase/Render) — riscritto per usare
// Supabase Auth al posto del flusso OAuth custom verso auth.emergentagent.com
// (session_id in redirect URL -> POST /auth/session sul backend Emergent).
//
// L'INTERFACCIA ESPORTATA (user, loading, login, loginEmail, register,
// loginApple, loginDemo, logout, refresh, setUser) è rimasta IDENTICA a
// quella precedente: le ~25 schermate che consumano solo user/setUser/
// logout/refresh/loading e app/onboarding.tsx (l'unica che chiama
// login/loginEmail/register/loginApple/loginDemo direttamente) non
// richiedono modifiche.
//
// Cosa cambia internamente:
// - loginEmail/register -> supabase.auth.signInWithPassword / signUp.
// - loginApple -> supabase.auth.signInWithIdToken({provider:'apple', token})
//   usando l'identityToken che expo-apple-authentication produce già
//   nativamente (nessun round-trip col backend prima del login, a differenza
//   della versione Emergent).
// - login(mode) (Google) -> supabase.auth.signInWithOAuth. Su web, Supabase
//   gestisce da solo il redirect e il parsing della sessione dall'URL di
//   ritorno (supabase.ts ha detectSessionInUrl:true per web) — non serve più
//   il parsing manuale di session_id che c'era prima. Su nativo si apre un
//   browser in-app (WebBrowser.openAuthSessionAsync) e si estrae la sessione
//   dai parametri access_token/refresh_token nell'URL di ritorno.
// - loginDemo() -> NON PORTATA IN QUESTO BLOCCO: la versione Emergent creava/
//   riusava un utente demo lato backend con un token fittizio; farlo con
//   Supabase Auth richiederebbe l'Admin API (service role) per provisionare
//   un utente demo reale, non disponibile qui. Lascio uno stub che lancia un
//   errore esplicito invece di fingere che funzioni — onDemo() in
//   onboarding.tsx già cattura l'errore silenziosamente.
// - Lo stato utente ora segue supabase.auth.onAuthStateChange invece di un
//   controllo one-shot al mount: qualunque cambio di sessione (login,
//   logout, refresh del token scaduto) fa ripartire refresh() automaticamente.
import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";
import * as WebBrowser from "expo-web-browser";
import * as Linking from "expo-linking";
import { Platform } from "react-native";
import { router } from "expo-router";
import { supabase } from "@/src/lib/supabase";
import { api, setUnauthorizedHandler } from "@/src/api";

WebBrowser.maybeCompleteAuthSession();

type User = any;
type AuthState = {
  user: User | null;
  loading: boolean;
  login: (mode?: "signup" | "signin") => Promise<void>;
  loginEmail: (email: string, password: string) => Promise<any>;
  register: (email: string, password: string, name: string) => Promise<any>;
  loginApple: (identityToken: string, name?: string | null, email?: string | null) => Promise<any>;
  loginDemo: () => Promise<any>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  setUser: (u: User) => void;
};

const AuthContext = createContext<AuthState>({} as AuthState);
export const useAuth = () => useContext(AuthContext);

// Le schermate esistenti (onboarding.tsx) si aspettano messaggi d'errore che
// contengono certe parole chiave inglesi (email_exists, weak_password,
// invalid_email, invalid_credentials, not_registered — vedi mapError() lì).
// I messaggi che Supabase Auth restituisce sono diversi (e in inglese
// discorsivo), quindi li traduciamo qui per non dover toccare onboarding.tsx.
// NOTA: Supabase, per policy di sicurezza, risponde "Invalid login
// credentials" sia per password sbagliata sia per email non registrata (a
// differenza della versione Emergent che distingueva "not_registered") — non
// è possibile distinguere i due casi lato client, quindi entrambi mappano su
// invalid_credentials.
function mapSupabaseAuthError(err: any): Error {
  const msg = String(err?.message || err || "");
  const lower = msg.toLowerCase();
  if (lower.includes("already registered") || lower.includes("already exists")) {
    return new Error("email_exists");
  }
  if (lower.includes("password") && (lower.includes("least") || lower.includes("short") || lower.includes("weak"))) {
    return new Error("weak_password");
  }
  if (lower.includes("invalid") && lower.includes("email")) {
    return new Error("invalid_email");
  }
  if (lower.includes("invalid login credentials") || lower.includes("invalid credentials")) {
    return new Error("invalid_credentials");
  }
  return new Error(msg || "auth_error");
}

// Estrae access_token/refresh_token dai parametri (hash o query) di un URL di
// ritorno da un provider OAuth e li imposta come sessione Supabase corrente.
async function createSessionFromUrl(url: string) {
  const part = url.split("#")[1] || url.split("?")[1] || "";
  const params = new URLSearchParams(part);
  const access_token = params.get("access_token");
  const refresh_token = params.get("refresh_token");
  if (!access_token || !refresh_token) return null;
  const { data, error } = await supabase.auth.setSession({ access_token, refresh_token });
  if (error) throw mapSupabaseAuthError(error);
  return data.session;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  // Evita refresh() concorrenti/ridondanti quando onAuthStateChange spara più
  // eventi ravvicinati (es. INITIAL_SESSION seguito subito da SIGNED_IN).
  const refreshing = useRef(false);

  const refresh = useCallback(async () => {
    if (refreshing.current) return;
    refreshing.current = true;
    try {
      const me = await api.me();
      setUser(me);
    } catch {
      setUser(null);
    } finally {
      refreshing.current = false;
    }
  }, []);

  // Sessione scaduta/non valida (401 dal backend) → logout pulito + redirect
  // al login invece di far crashare l'app.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      try { router.replace("/onboarding"); } catch {}
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  // Segue lo stato della sessione Supabase Auth: al primo mount emette subito
  // INITIAL_SESSION con la sessione persistita (o null), poi ogni SIGNED_IN /
  // SIGNED_OUT / TOKEN_REFRESHED successivo.
  useEffect(() => {
    let mounted = true;
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!mounted) return;
      if (session) {
        refresh().finally(() => setLoading(false));
      } else {
        setUser(null);
        setLoading(false);
      }
    });
    return () => {
      mounted = false;
      subscription.subscription.unsubscribe();
    };
  }, [refresh]);

  const login = useCallback(async (_mode: "signup" | "signin" = "signup") => {
    const isWeb = Platform.OS === "web" && typeof window !== "undefined";
    const redirectTo = isWeb ? window.location.origin + "/" : Linking.createURL("");

    if (isWeb) {
      // Su web Supabase fa il redirect da solo; al ritorno detectSessionInUrl
      // (impostato in src/lib/supabase.ts) crea la sessione automaticamente e
      // l'onAuthStateChange sopra aggiorna `user`.
      const { error } = await supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo } });
      if (error) throw mapSupabaseAuthError(error);
      return;
    }

    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo, skipBrowserRedirect: true },
    });
    if (error) throw mapSupabaseAuthError(error);
    if (!data?.url) throw new Error("auth_error");
    const result = await WebBrowser.openAuthSessionAsync(data.url, redirectTo);
    if (result.type === "success" && result.url) {
      await createSessionFromUrl(result.url);
    }
  }, []);

  const logout = useCallback(async () => {
    try { await api.logout(); } catch {}
    await supabase.auth.signOut();
    setUser(null);
  }, []);

  const loginEmail = useCallback(async (email: string, password: string) => {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw mapSupabaseAuthError(error);
    await refresh();
    return data.user;
  }, [refresh]);

  const register = useCallback(async (email: string, password: string, name: string) => {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { full_name: name } },
    });
    if (error) throw mapSupabaseAuthError(error);
    // Con conferma email disattivata, signUp restituisce già una sessione
    // valida; con conferma email attiva (da verificare in Supabase Dashboard
    // -> Auth -> Providers), session sarà null finché l'utente non conferma:
    // in quel caso onAuthStateChange non scatterà finché non torna a fare
    // login dopo la conferma.
    if (data.session) await refresh();
    return data.user;
  }, [refresh]);

  const loginApple = useCallback(async (identityToken: string, name?: string | null, email?: string | null) => {
    const { data, error } = await supabase.auth.signInWithIdToken({
      provider: "apple",
      token: identityToken,
    });
    if (error) throw mapSupabaseAuthError(error);
    // Apple restituisce nome/email solo al PRIMO login: se presenti e il
    // profilo Supabase non ha ancora un nome, li salviamo nei metadata utente
    // cosicché il trigger di onboarding/i profili possano usarli in seguito.
    if (name) {
      try { await supabase.auth.updateUser({ data: { full_name: name } }); } catch {}
    }
    await refresh();
    return data.user;
  }, [refresh]);

  const loginDemo = useCallback(async () => {
    // Non portata in questo blocco — vedi commento in testa al file.
    throw new Error("demo_not_available");
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, loginEmail, register, loginApple, loginDemo, logout, refresh, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}
