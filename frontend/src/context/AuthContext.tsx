import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import * as WebBrowser from "expo-web-browser";
import * as Linking from "expo-linking";
import { Platform } from "react-native";
import { api, setToken, clearToken, getToken } from "@/src/api";

WebBrowser.maybeCompleteAuthSession();

type User = any;
type AuthState = {
  user: User | null;
  loading: boolean;
  login: () => Promise<void>;
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

async function processSessionId(sessionId: string) {
  // Send the one-time session_id straight to our backend, which exchanges it
  // with Emergent's session-data endpoint and returns a persistent token.
  const backend = await api.createSession(sessionId);
  await setToken(backend.session_token);
  return backend.user;
}

function extractSessionId(url: string): string | null {
  if (!url) return null;
  const hashMatch = url.match(/#.*session_id=([^&]+)/);
  if (hashMatch) return decodeURIComponent(hashMatch[1]);
  const queryMatch = url.match(/[?&]session_id=([^&]+)/);
  if (queryMatch) return decodeURIComponent(queryMatch[1]);
  return null;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const me = await api.me();
      setUser(me);
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        // Web: check URL for session_id first
        if (Platform.OS === "web" && typeof window !== "undefined") {
          const sid = extractSessionId(window.location.href);
          if (sid) {
            const u = await processSessionId(sid);
            setUser(u);
            window.history.replaceState(null, "", window.location.pathname);
            setLoading(false);
            return;
          }
        } else {
          const initial = await Linking.getInitialURL();
          const sid = initial ? extractSessionId(initial) : null;
          if (sid) {
            const u = await processSessionId(sid);
            setUser(u);
            setLoading(false);
            return;
          }
        }
        const token = await getToken();
        if (token) await refresh();
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    })();
  }, [refresh]);

  const login = useCallback(async () => {
    const redirectUrl =
      Platform.OS === "web" && typeof window !== "undefined"
        ? window.location.origin + "/"
        : Linking.createURL("");
    const authUrl = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;

    if (Platform.OS === "web" && typeof window !== "undefined") {
      window.location.href = authUrl;
      return;
    }
    const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
    if (result.type === "success" && result.url) {
      const sid = extractSessionId(result.url);
      if (sid) {
        const u = await processSessionId(sid);
        setUser(u);
      }
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {}
    await clearToken();
    setUser(null);
  }, []);

  const loginEmail = useCallback(async (email: string, password: string) => {
    const res = await api.loginEmail({ email, password });
    await setToken(res.session_token);
    setUser(res.user);
    return res.user;
  }, []);

  const register = useCallback(async (email: string, password: string, name: string) => {
    const res = await api.register({ email, password, name });
    await setToken(res.session_token);
    setUser(res.user);
    return res.user;
  }, []);

  const loginApple = useCallback(async (identityToken: string, name?: string | null, email?: string | null) => {
    const res = await api.loginApple({ identity_token: identityToken, name, email });
    await setToken(res.session_token);
    setUser(res.user);
    return res.user;
  }, []);

  const loginDemo = useCallback(async () => {
    const res = await api.loginDemo();
    await setToken(res.session_token);
    setUser(res.user);
    return res.user;
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, loginEmail, register, loginApple, loginDemo, logout, refresh, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}
